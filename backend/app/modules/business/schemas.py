# Request and response shapes for sign-up and Services. The backend owns all validation
# rules; each message here is shown next to its field on the form.
import uuid

from pydantic import BaseModel, Field, StrictInt, field_validator
from pydantic_core import PydanticCustomError

from app.modules.accounts import service as accounts_service
from app.modules.business.models import MAX_DURATION, MAX_PRICE_PAISE, MIN_DURATION

MAX_NAME = 100


class SignupRequest(BaseModel):
    business_name: str
    email: str
    password: str

    @field_validator("business_name")
    @classmethod
    def clean_business_name(cls, value: str) -> str:
        value = value.strip()
        # Postgres cannot store the NUL character (\x00), so refuse it here as a field error.
        if not value or "\x00" in value:
            raise PydanticCustomError("business_name_empty", "Enter your business name.")
        if len(value) > MAX_NAME:
            raise PydanticCustomError("business_name_long", "Use at most 100 characters.")
        return value

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        # One rule for sign-up and log-in, owned by accounts (D8).
        return accounts_service.clean_email(value)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        # One rule for sign-up and invite-accept, owned by accounts (story 2.5).
        return accounts_service.check_new_password(value)


class SignupResponse(BaseModel):
    business_id: uuid.UUID
    business_name: str


# ---------------------------------------------------------------- services (story 3.1, FR-12)


class ServiceIn(BaseModel):
    """A whole Service, for add (POST) and replace (PUT). Every field must be sent.

    One schema for both, so "save" and "activate" pass the same rules (FR-12:
    a Service cannot be saved OR activated without a Price).
    """

    name: str
    # StrictInt: only real JSON whole numbers. Plain int would turn `true` into 1 paise.
    # default=None + validate_default=True: a missing field reaches the validator too,
    # so the Owner sees our own message, not the generic "This field is required."
    duration_minutes: StrictInt | None = Field(default=None, validate_default=True)
    price_paise: StrictInt | None = Field(default=None, validate_default=True)
    is_active: bool  # no default: a replace must not quietly turn a Service back on

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        # Postgres cannot store the NUL character (\x00), so refuse it here as a field error.
        if not value or "\x00" in value:
            raise PydanticCustomError("service_name_empty", "Enter a name for the Service.")
        if len(value) > MAX_NAME:
            raise PydanticCustomError("service_name_long", "Use at most 100 characters.")
        return value

    @field_validator("duration_minutes")
    @classmethod
    def check_duration(cls, value: int | None) -> int:
        if value is None:
            raise PydanticCustomError("duration_missing", "Enter a duration in minutes.")
        if not MIN_DURATION <= value <= MAX_DURATION:
            raise PydanticCustomError("duration_range", "Use 30 to 480 minutes.")
        return value

    @field_validator("price_paise")
    @classmethod
    def check_price(cls, value: int | None) -> int:
        if value is None:
            raise PydanticCustomError("price_missing", "Enter a Price in rupees, for example 499.")
        if value <= 0:
            raise PydanticCustomError("price_too_low", "Enter a Price above ₹0.")
        # Also stops numbers too big for the database column, which would crash with a 500.
        if value > MAX_PRICE_PAISE:
            raise PydanticCustomError("price_too_high", "Use at most ₹10,00,000.")
        return value


class ServiceOut(BaseModel):
    service_id: uuid.UUID
    name: str
    duration_minutes: int
    price_paise: int  # whole paise: ₹499 = 49900 (AR-5)
    is_active: bool


class ServiceList(BaseModel):
    # An object, not a bare list, so fields can be added later without breaking the app.
    services: list[ServiceOut]  # oldest first

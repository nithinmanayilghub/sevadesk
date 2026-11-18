# Request and response shapes for sign-up. The backend owns all validation rules;
# each message here is shown next to its field on the sign-up form.
import uuid

from pydantic import BaseModel, field_validator
from pydantic_core import PydanticCustomError

from app.modules.accounts import service as accounts_service

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

# Request and response shapes for sign-up and Services. The backend owns all validation
# rules; each message here is shown next to its field on the form.
import re
import uuid
from datetime import date, time

from pydantic import BaseModel, Field, StrictInt, ValidationInfo, field_validator
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


# ---------------------------------------------------------------- working hours (story 3.2, FR-13)

# Index = the weekday number stored in the database (0 = Monday, Python's date.weekday()).
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# "10:00" or "10:00:00", 24-hour, whole minutes only. No seconds, no UTC offset: a clock time
# in the Business timezone. "9:00" and "24:00" do not match. [0-9], not \d: \d also matches
# digits from other scripts (e.g. "1٠:00"), which time.fromisoformat cannot read.
_TIME_TEXT = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9](:00)?")


def _parse_time(value: object) -> time:
    """What the form sent -> a clock time. Anything else (a number, bad text) -> our own message."""
    if not isinstance(value, str) or not _TIME_TEXT.fullmatch(value):
        raise PydanticCustomError("time_invalid", "Use a time like 10:00.")
    return time.fromisoformat(value)


class DayIn(BaseModel):
    """One OPEN day, as the form sends it. A closed day is sent as null instead.

    mode="before": our validator sees the raw JSON value first, so every bad input (text,
    a number, null) gets our own message, and the field then really holds a `time`.
    default=None + validate_default=True: an empty box (or a missing key) reaches it too.
    """

    start_time: time | None = Field(default=None, validate_default=True)
    end_time: time | None = Field(default=None, validate_default=True)

    @field_validator("start_time", mode="before")
    @classmethod
    def check_start(cls, value: object) -> time:
        if value is None:
            raise PydanticCustomError("start_missing", "Enter a start time.")
        return _parse_time(value)

    # A field validator (not a model validator), so the error lands on "<day>.end_time".
    @field_validator("end_time", mode="before")
    @classmethod
    def check_end(cls, value: object, info: ValidationInfo) -> time:
        if value is None:
            raise PydanticCustomError("end_missing", "Enter an end time.")
        end = _parse_time(value)
        # A refused start time is not in info.data, so there is nothing to compare with.
        start = info.data.get("start_time")
        if start is not None and end <= start:
            raise PydanticCustomError("end_not_after_start", "End time must be after the start time.")
        return end


class WeekIn(BaseModel):
    """The whole week, for a full replace (PUT). Every day must be sent; null = closed."""

    monday: DayIn | None
    tuesday: DayIn | None
    wednesday: DayIn | None
    thursday: DayIn | None
    friday: DayIn | None
    saturday: DayIn | None
    sunday: DayIn | None


class OpenHours(BaseModel):
    """The hours of one open day. Both times are always there."""

    start_time: time
    end_time: time


class WorkingHoursOut(BaseModel):
    timezone: str  # how to read the times, e.g. "Asia/Kolkata" (AR-5)
    monday: OpenHours | None  # None = closed
    tuesday: OpenHours | None
    wednesday: OpenHours | None
    thursday: OpenHours | None
    friday: OpenHours | None
    saturday: OpenHours | None
    sunday: OpenHours | None


# ---------------------------------------------------------------- closed days (story 3.2, FR-13)

_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")  # "2026-12-25" only: no time part


class ClosedDayIn(BaseModel):
    # mode="before", as in DayIn: every bad input gets "Pick a date.", and `day` holds a date.
    day: date | None = Field(default=None, validate_default=True)

    @field_validator("day", mode="before")
    @classmethod
    def check_day(cls, value: object) -> date:
        if not isinstance(value, str) or not _DATE_TEXT.fullmatch(value):
            raise PydanticCustomError("day_invalid", "Pick a date.")
        try:
            return date.fromisoformat(value)
        except ValueError:  # the right shape, but no such day, e.g. 2026-02-30
            raise PydanticCustomError("day_invalid", "Pick a date.") from None


class ClosedDayOut(BaseModel):
    closed_day_id: uuid.UUID
    day: date


class ClosedDayList(BaseModel):
    closed_days: list[ClosedDayOut]  # today onward, soonest first


# ---------------------------------------------------------------- chat page (story 3.3, FR-14)


class SetupOut(BaseModel):
    """What the Owner's Dashboard checklist needs: the chat link and what is still missing."""

    chat_slug: str  # the link is /c/{chat_slug}
    has_services: bool  # at least one ACTIVE Service
    has_working_hours: bool  # at least one open weekday


class ChatBusiness(BaseModel):
    """The Business a public chat route works for, found from the slug (AD-3 b). Server-side only."""

    business_id: uuid.UUID
    name: str


class ChatServiceOut(BaseModel):
    # What a Customer may see. No id and no is_active: the public page needs neither.
    name: str
    duration_minutes: int
    price_paise: int


class ChatPageOut(BaseModel):
    business_name: str
    # False until the Business has an active Service AND Working Hours.
    taking_requests: bool
    services: list[ChatServiceOut]  # active only, oldest first

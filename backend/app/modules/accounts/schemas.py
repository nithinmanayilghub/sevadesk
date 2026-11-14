# DTOs (plain data objects) that the accounts front door returns to other modules (AD-2).
import uuid
from enum import StrEnum

from pydantic import BaseModel, field_validator
from pydantic_core import PydanticCustomError

from app.modules.accounts.emails import clean_email

MAX_PASSWORD = 128


class Role(StrEnum):
    OWNER = "owner"
    STAFF = "staff"
    TECHNICIAN = "technician"


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return clean_email(value)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        # No length rule beyond the upper cap: telling attackers the policy helps no one here.
        if not value:
            raise PydanticCustomError("password_empty", "Enter your password.")
        # The same cap as sign-up. It stops a huge password from costing a lot of Argon2 work.
        if len(value) > MAX_PASSWORD:
            raise PydanticCustomError("password_long", "Use at most 128 characters.")
        return value


class MeResponse(BaseModel):
    """What the app needs to know about the logged-in User: their Roles, for the nav."""

    roles: list[Role]


class Actor(BaseModel):
    """Who is making this request, built from their session (AD-4). Services check Roles on it."""

    user_id: uuid.UUID
    membership_id: uuid.UUID
    business_id: uuid.UUID
    roles: set[Role]


class OwnerCreated(BaseModel):
    user_id: uuid.UUID
    membership_id: uuid.UUID
    roles: set[Role]

# DTOs (plain data objects) that the accounts front door returns to other modules (AD-2).
import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, field_validator
from pydantic_core import PydanticCustomError

from app.modules.accounts.emails import clean_email

MIN_PASSWORD = 12
MAX_PASSWORD = 128


def check_new_password(value: str) -> str:
    """The rule for a NEW password (sign-up and invite-accept). Length only, no "must have a digit".

    Not stripped: spaces are part of the password.
    """
    if len(value) < MIN_PASSWORD:
        raise PydanticCustomError("password_short", "Use at least 12 characters.")
    if len(value) > MAX_PASSWORD:
        raise PydanticCustomError("password_long", "Use at most 128 characters.")
    return value


class Role(StrEnum):
    OWNER = "owner"
    STAFF = "staff"
    TECHNICIAN = "technician"


class Permission(StrEnum):
    """One member per row of the FR-10 table. permissions.py says which Roles may do each.

    A later action with no FR-10 row (e.g. delete a Customer) adds its own member.
    """

    MANAGE_SETUP = "manage_setup"  # Services, Working Hours, and team
    USE_INBOX_AND_BOOKINGS = "use_inbox_and_bookings"  # the Inbox, and approve Bookings
    SEE_OWN_BOOKINGS = "see_own_bookings"  # the Bookings assigned to you
    SEE_DASHBOARD = "see_dashboard"


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
    """What the app needs to know about the logged-in User: their Roles, and what they may do.

    The app shows or hides nav items and pages from `permissions` (UX-DR27). It never
    works the rules out itself: the FR-10 table lives only in the backend (AD-5).
    """

    roles: list[Role]
    permissions: list[Permission]


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


# ---------------------------------------------------------------- team (story 2.5, FR-9)

# The Roles an Owner may give through an invite. The MVP has one Owner per Business.
TEAM_ROLES: frozenset[Role] = frozenset({Role.STAFF, Role.TECHNICIAN})


class InviteRequest(BaseModel):
    email: str
    roles: list[Role]

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return clean_email(value)

    @field_validator("roles")
    @classmethod
    def check_roles(cls, value: list[Role]) -> list[Role]:
        if not value:
            raise PydanticCustomError("roles_empty", "Choose at least one Role.")
        if not set(value) <= TEAM_ROLES:
            raise PydanticCustomError("roles_not_allowed", "Choose Staff, Technician, or both.")
        return sorted(set(value))  # no duplicates, one fixed order


class InviteCreated(BaseModel):
    """The raw token, shown ONCE. The database keeps only its hash."""

    token: str
    expires_at: datetime

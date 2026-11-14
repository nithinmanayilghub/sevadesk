# DTOs (plain data objects) that the accounts front door returns to other modules (AD-2).
import uuid
from enum import StrEnum

from pydantic import BaseModel


class Role(StrEnum):
    OWNER = "owner"
    STAFF = "staff"
    TECHNICIAN = "technician"


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

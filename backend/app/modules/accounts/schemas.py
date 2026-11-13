# DTOs (plain data objects) that the accounts front door returns to other modules (AD-2).
import uuid
from enum import StrEnum

from pydantic import BaseModel


class Role(StrEnum):
    OWNER = "owner"
    STAFF = "staff"
    TECHNICIAN = "technician"


class OwnerCreated(BaseModel):
    user_id: uuid.UUID
    membership_id: uuid.UUID
    roles: set[Role]

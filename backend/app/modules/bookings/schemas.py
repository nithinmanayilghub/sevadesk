# The shapes (DTOs) that the bookings front door gives to routes and other modules (AD-2).
from datetime import datetime

from pydantic import BaseModel


class SlotOut(BaseModel):
    """One free time for one Service. Both moments are in UTC; show them in `timezone`."""

    start: datetime
    end: datetime


class FreeSlotsOut(BaseModel):
    timezone: str  # the Business timezone, e.g. "Asia/Kolkata": show Slots in it (UX-DR4)
    slots: list[SlotOut]  # earliest first

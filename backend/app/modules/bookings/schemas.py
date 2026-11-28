# The shapes (DTOs) that the bookings front door gives to routes and other modules (AD-2).
import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel

from app.modules.accounts.schemas import TechnicianOut
from app.modules.business.schemas import ServiceOut


class SlotOut(BaseModel):
    """One free time for one Service. Both moments are in UTC; show them in `timezone`."""

    start: datetime
    end: datetime


class FreeSlotsOut(BaseModel):
    timezone: str  # the Business timezone, e.g. "Asia/Kolkata": show Slots in it (UX-DR4)
    slots: list[SlotOut]  # earliest first


class NewBooking(BaseModel):
    """What a caller (inbox) gives create_confirmed (story 5.2). The caller found the Customer."""

    customer_id: uuid.UUID
    conversation_id: uuid.UUID | None  # None for a phone-in Booking (FR-27)
    service_id: uuid.UUID
    starts_at: AwareDatetime  # a moment WITH a timezone: never guess one (AR-5)
    technician_membership_id: uuid.UUID | None  # None = "pick for me" (only with one Technician)


class BookingOut(BaseModel):
    """One Booking, as routes and other modules see it."""

    booking_id: uuid.UUID
    state: str
    starts_at: datetime  # UTC
    ends_at: datetime  # UTC
    service_id: uuid.UUID
    customer_id: uuid.UUID
    conversation_id: uuid.UUID | None
    technician_membership_id: uuid.UUID | None
    price_paise: int


class BookingOptionsOut(BaseModel):
    """What the booking form needs before the Slots (story 5.2). The Slots come per Service."""

    services: list[ServiceOut]  # active only, oldest first
    # Active Technicians, oldest first. With exactly one, the form shows no picker (UX-DR29).
    technicians: list[TechnicianOut]

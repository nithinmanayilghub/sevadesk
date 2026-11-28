# The bookings front door (AD-2). Other modules and routes call only these functions.
# - list_free_slots (story 5.1, FR-17): the free Slots of one Service for the next 7 days.
# - create_confirmed (story 5.2, FR-27): THE write path for a confirmed Booking (AD-9).
#
# How it gets its facts: the Service and the Working Hours from business, the active
# Technicians from accounts (AR-7), and the live Bookings from its own repository. Then the
# pure function in slots.py does the math.
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from opentelemetry import trace
from sqlalchemy.orm import Session

from app.core.errors import AppError, FieldError

# Import the modules, not the functions, so every call goes through <module>_service.<name>.
from app.modules.accounts import service as accounts_service
from app.modules.accounts.schemas import Actor, Permission
from app.modules.bookings.models import Booking
from app.modules.bookings.repository import BookingRepository
from app.modules.bookings.schemas import BookingOut, FreeSlotsOut, NewBooking, SlotOut
from app.modules.bookings.slots import free_slots, window_days
from app.modules.business import service as business_service
from app.modules.business.schemas import ServiceOut


class SlotUnavailable(AppError):
    """409: this time is not free (any more). AD-9 names this error."""

    def __init__(self):
        super().__init__(
            code="slot_unavailable", message="This time is no longer free. Pick another time.", status_code=409
        )


class TechnicianBusy(AppError):
    """409: the shop has room, but the PICKED Technician already has a job then."""

    def __init__(self):
        super().__init__(
            code="technician_busy",
            message="This Technician already has a job at this time. Pick another Technician or time.",
            status_code=409,
        )


def _technician_error(message: str) -> AppError:
    """A 422 on the Technician field, in the normal envelope, so the form shows it next to the picker."""
    return AppError(
        code="validation_error",
        message="Some fields need fixing.",
        status_code=422,
        fields=[FieldError(field="technician_membership_id", message=message)],
    )


def _now() -> datetime:
    """The current moment in UTC. The one clock of bookings, so tests can replace it."""
    return datetime.now(UTC)


def _free_slots(session: Session, service: ServiceOut, tz: ZoneInfo, now: datetime) -> list[SlotOut]:
    """The free Slots of one Service, today and the next 6 days, on the Business clock.

    ONE code path for the Slot list AND the recount before a write (AD-9): a time is bookable
    exactly when the list would show it.
    """
    # "Today" is the Business's date: at 00:30 in India it is still yesterday in UTC (AR-5).
    days = window_days(now.astimezone(tz).date())
    hours_by_day = {day: business_service.hours_on(session, day) for day in days}

    # One query for the whole window, from the first day's midnight to the day after the last.
    window_start = datetime.combine(days[0], time.min, tzinfo=tz)
    window_end = datetime.combine(days[-1] + timedelta(days=1), time.min, tzinfo=tz)
    busy = BookingRepository(session).live_between(window_start, window_end, now)

    return free_slots(
        hours_by_day=hours_by_day,
        duration=timedelta(minutes=service.duration_minutes),
        busy=busy,
        technician_count=len(accounts_service.active_technician_ids(session)),
        tz=tz,
        now=now,
    )


def list_free_slots(session: Session, actor: Actor, service_id: uuid.UUID) -> FreeSlotsOut:
    """The free Slots of one Service, today and the next 6 days, on the Business clock.

    Owner and Staff only (FR-10): a Technician-only User gets Forbidden (403).
    An unknown, deactivated, or other Business's Service gives NotFound (404).
    """
    accounts_service.require_roles(actor, Permission.USE_INBOX_AND_BOOKINGS)
    service = business_service.get_active_service(session, service_id)
    timezone = business_service.business_timezone(session)
    slots = _free_slots(session, service, ZoneInfo(timezone), _now())
    return FreeSlotsOut(timezone=timezone, slots=slots)


def _choose_technician(session: Session, picked: uuid.UUID | None) -> uuid.UUID:
    """Who does the job. With one active Technician, nobody has to pick (UX-DR29)."""
    active = accounts_service.active_technician_ids(session)
    if picked is None:
        if len(active) == 1:
            return active[0]
        # 2+ Technicians: we never guess who goes. (0 cannot get here: then no Slot is free.)
        raise _technician_error("Pick a Technician.")
    # A deactivated member, a non-Technician, or another Business's id: none is in this list.
    if picked not in active:
        raise _technician_error("Pick an active Technician.")
    return picked


def create_confirmed(session: Session, actor: Actor, data: NewBooking) -> BookingOut:
    """Save a confirmed Booking in a free Slot (FR-27). The ONE write path for it (AD-9).

    Steps, in this order:
    1. Role check first (FR-10): a Technician-only User learns nothing.
    2. The Service must be active and ours (404 otherwise).
    3. The recount: the time must be one of the free Slots RIGHT NOW (else SlotUnavailable).
    4. The Technician: chosen or checked, and not busy then (else 422 / TechnicianBusy).
    No commit here: the request owns the transaction (AD-15).
    """
    accounts_service.require_roles(actor, Permission.USE_INBOX_AND_BOOKINGS)
    service = business_service.get_active_service(session, data.service_id)
    tz = ZoneInfo(business_service.business_timezone(session))

    # Aware datetimes compare by the real moment: 10:00+05:30 equals 04:30Z.
    free_starts = {slot.start for slot in _free_slots(session, service, tz, _now())}
    if data.starts_at not in free_starts:
        raise SlotUnavailable()

    starts_at = data.starts_at.astimezone(UTC)
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)
    technician_id = _choose_technician(session, data.technician_membership_id)
    bookings = BookingRepository(session)
    if bookings.technician_busy(technician_id, starts_at, ends_at):
        raise TechnicianBusy()

    row = bookings.add(
        Booking(
            state="confirmed",
            starts_at=starts_at,
            ends_at=ends_at,
            customer_id=data.customer_id,
            conversation_id=data.conversation_id,
            technician_membership_id=technician_id,
            service_id=service.service_id,
            # The Price is copied from the Service now: a later Price change leaves this job alone.
            price_paise=service.price_paise,
            expires_at=None,
        )
    )
    # A note in this request's trace: no ids, no name, no phone (AD-13).
    trace.get_current_span().add_event(
        "booking.created", {"state": row.state, "from_conversation": data.conversation_id is not None}
    )
    return BookingOut(
        booking_id=row.id,
        state=row.state,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        service_id=row.service_id,
        customer_id=row.customer_id,
        conversation_id=row.conversation_id,
        technician_membership_id=row.technician_membership_id,
        price_paise=row.price_paise,
    )

# The bookings front door (AD-2). Other modules and routes call only these functions.
# - list_free_slots (story 5.1, FR-17): the free Slots of one Service for the next 7 days.
#
# How it gets its facts: the Service and the Working Hours from business, the active
# Technicians from accounts (AR-7), and the live Bookings from its own repository. Then the
# pure function in slots.py does the math.
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

# Import the modules, not the functions, so every call goes through <module>_service.<name>.
from app.modules.accounts import service as accounts_service
from app.modules.accounts.schemas import Actor, Permission
from app.modules.bookings.repository import BookingRepository
from app.modules.bookings.schemas import FreeSlotsOut
from app.modules.bookings.slots import free_slots, window_days
from app.modules.business import service as business_service


def _now() -> datetime:
    """The current moment in UTC. The one clock of bookings, so tests can replace it."""
    return datetime.now(UTC)


def list_free_slots(session: Session, actor: Actor, service_id: uuid.UUID) -> FreeSlotsOut:
    """The free Slots of one Service, today and the next 6 days, on the Business clock.

    Owner and Staff only (FR-10): a Technician-only User gets Forbidden (403).
    An unknown, deactivated, or other Business's Service gives NotFound (404).
    """
    accounts_service.require_roles(actor, Permission.USE_INBOX_AND_BOOKINGS)
    service = business_service.get_active_service(session, service_id)
    timezone = business_service.business_timezone(session)
    tz = ZoneInfo(timezone)
    now = _now()

    # "Today" is the Business's date: at 00:30 in India it is still yesterday in UTC (AR-5).
    days = window_days(now.astimezone(tz).date())
    hours_by_day = {day: business_service.hours_on(session, day) for day in days}

    # One query for the whole window, from the first day's midnight to the day after the last.
    window_start = datetime.combine(days[0], time.min, tzinfo=tz)
    window_end = datetime.combine(days[-1] + timedelta(days=1), time.min, tzinfo=tz)
    busy = BookingRepository(session).live_between(window_start, window_end, now)

    slots = free_slots(
        hours_by_day=hours_by_day,
        duration=timedelta(minutes=service.duration_minutes),
        busy=busy,
        technicians=len(accounts_service.active_technician_ids(session)),
        tz=tz,
        now=now,
    )
    return FreeSlotsOut(timezone=timezone, slots=slots)

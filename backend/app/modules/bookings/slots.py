# The free-Slot math (story 5.1, FR-17). Pure: no database, no clock. Every input is given,
# so unit tests can check every rule with plain values.
#
# A Slot is free when ALL of these are true:
# 1. its day is open (not a closed day, and the weekday has Working Hours),
# 2. it starts on the step grid, counted from the opening time,
# 3. it ends at or before closing time (start + Service duration <= close),
# 4. it does not start in the past,
# 5. fewer live Bookings overlap it than there are active Technicians.
#    (One Technician does one job at a time. With 2 Technicians, 1 job still leaves room.)
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.modules.bookings.schemas import SlotOut
from app.modules.business.schemas import OpenHours

# Fixed constants (AR-24). The Slot LENGTH is the Service's own duration, so it is not a constant.
SLOT_STEP_MINUTES = 30  # Slots start at opening time, +30 min, +60 min, ...
SLOT_DAYS = 7  # how many days ahead we list: today and the next 6 days


def window_days(today: date) -> list[date]:
    """The dates we list Slots for. `today` must be the BUSINESS date, not the server date."""
    return [today + timedelta(days=offset) for offset in range(SLOT_DAYS)]


def _overlaps(busy: tuple[datetime, datetime], start: datetime, end: datetime) -> bool:
    # Half-open ranges [start, end): a job ending at 11:00 does NOT clash with a Slot at 11:00.
    busy_start, busy_end = busy
    return busy_start < end and busy_end > start


def free_slots(
    *,
    hours_by_day: dict[date, OpenHours | None],
    duration: timedelta,
    busy: list[tuple[datetime, datetime]],
    technicians: int,
    tz: ZoneInfo,
    now: datetime,
) -> list[SlotOut]:
    """Every free Slot, earliest first, in UTC.

    hours_by_day: each date's open hours on the Business clock; None = closed.
    busy: (start, end) of every LIVE Booking (the repository already removed expired ones).
    technicians: how many active Technicians the Business has (from accounts, AR-7).
    """
    step = timedelta(minutes=SLOT_STEP_MINUTES)
    slots = []
    for day in sorted(hours_by_day):
        hours = hours_by_day[day]
        if hours is None:
            continue
        # Clock times become real moments in the Business timezone (AR-5), then UTC.
        # Why UTC before the math: "+ 30 min" on a clock time skips or repeats an hour on a
        # day when the clock jumps (DST). In UTC every step is 30 REAL minutes.
        start = datetime.combine(day, hours.start_time, tzinfo=tz).astimezone(UTC)
        close = datetime.combine(day, hours.end_time, tzinfo=tz).astimezone(UTC)
        while start + duration <= close:
            end = start + duration
            taken = sum(1 for job in busy if _overlaps(job, start, end))
            if start >= now and taken < technicians:
                slots.append(SlotOut(start=start, end=end))
            start += step
    return slots

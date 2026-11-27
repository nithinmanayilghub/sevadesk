# Unit tests: the pure free-Slot math (story 5.1, FR-17, AR-24). No database: every input is given.
# The test shop is in India (Asia/Kolkata, UTC+5:30), open 10:00-12:00, and the Service takes 60 min.
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.modules.bookings.slots import SLOT_DAYS, free_slots, window_days
from app.modules.business.schemas import OpenHours

TZ = ZoneInfo("Asia/Kolkata")
MONDAY = date(2026, 11, 30)
HOURS = OpenHours(start_time=time(10, 0), end_time=time(12, 0))
HOUR = timedelta(minutes=60)
SUNDAY_MIDNIGHT = datetime(2026, 11, 29, 0, 0, tzinfo=TZ)  # a "now" long before Monday


def ist(day: date, clock: str) -> datetime:
    """A moment on the shop's clock, e.g. ist(MONDAY, "10:30")."""
    return datetime.combine(day, time.fromisoformat(clock), tzinfo=TZ)


def starts(**changes) -> list[str]:
    """Run free_slots with the test shop; return the local start times as "HH:MM"."""
    inputs = {
        "hours_by_day": {MONDAY: HOURS},
        "duration": HOUR,
        "busy": [],
        "technicians": 1,
        "tz": TZ,
        "now": SUNDAY_MIDNIGHT,
    } | changes
    return [slot.start.astimezone(TZ).strftime("%H:%M") for slot in free_slots(**inputs)]


def test_open_day_gives_every_fitting_start():
    # 11:30 would end at 12:30, after closing, so it is not a Slot.
    assert starts() == ["10:00", "10:30", "11:00"]


def test_closed_day_gives_no_slots():
    assert starts(hours_by_day={MONDAY: None}) == []


def test_slot_at_end_of_working_hours():
    slots = free_slots(hours_by_day={MONDAY: HOURS}, duration=HOUR, busy=[], technicians=1, tz=TZ, now=SUNDAY_MIDNIGHT)
    assert slots[-1].end == ist(MONDAY, "12:00")  # ends exactly at closing time


def test_one_technician_fully_booked():
    assert starts(busy=[(ist(MONDAY, "10:00"), ist(MONDAY, "12:00"))]) == []


def test_two_technicians_one_free():
    one_job = [(ist(MONDAY, "10:00"), ist(MONDAY, "12:00"))]
    assert starts(technicians=2, busy=one_job) == ["10:00", "10:30", "11:00"]
    assert starts(technicians=2, busy=one_job * 2) == []


def test_touching_booking_does_not_block():
    # The job ends at 11:00; a Slot that starts at 11:00 does not overlap it.
    assert starts(busy=[(ist(MONDAY, "10:00"), ist(MONDAY, "11:00"))]) == ["11:00"]
    # The job starts at 11:00; the Slot 10:00-11:00 ends there, so it is free too.
    assert starts(busy=[(ist(MONDAY, "11:00"), ist(MONDAY, "12:00"))]) == ["10:00"]


def test_no_technicians_means_no_slots():
    assert starts(technicians=0) == []


def test_slots_before_now_are_dropped():
    assert starts(now=ist(MONDAY, "10:15")) == ["10:30", "11:00"]


def test_today_is_the_business_date_after_midnight():
    # 19:00 UTC on Sunday is already 00:30 on Monday in India.
    now = datetime(2026, 11, 29, 19, 0, tzinfo=UTC)
    days = window_days(now.astimezone(TZ).date())
    assert days[0] == MONDAY
    assert len(days) == SLOT_DAYS == 7


def test_slots_are_utc():
    first = free_slots(hours_by_day={MONDAY: HOURS}, duration=HOUR, busy=[], technicians=1, tz=TZ, now=SUNDAY_MIDNIGHT)[
        0
    ]
    assert first.start == datetime(2026, 11, 30, 4, 30, tzinfo=UTC)  # 10:00 in India
    assert first.start.tzinfo == UTC

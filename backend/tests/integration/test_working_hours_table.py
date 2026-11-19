# Database guards for the working_hours and closed_days tables, and the Business timezone
# (story 3.2, FR-13, AR-5). These tests write rows directly, past the API, to prove the
# database ITSELF refuses bad data. The API checks the same rules first (test_working_hours.py).
import uuid
from datetime import date, time

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.modules.business.models import Business, ClosedDay, WorkingHours


def insert(*rows) -> None:
    """Save rows in their OWN session: a failed INSERT spoils a session until rollback."""
    with Session(get_engine()) as session, session.begin():
        session.add_all(rows)


def hours(business_id: uuid.UUID, weekday: int = 0, start: time = time(10), end: time = time(18)) -> WorkingHours:
    return WorkingHours(business_id=business_id, weekday=weekday, start_time=start, end_time=end)


def test_new_business_timezone_is_asia_kolkata(sign_up_owner):
    # Sign-up goes through the ORM, so this also proves the model sends no NULL timezone.
    _, business_id = sign_up_owner()
    with Session(get_engine()) as session:
        assert session.get(Business, business_id).timezone == "Asia/Kolkata"


@pytest.mark.parametrize(("start", "end"), [(time(10), time(10)), (time(18), time(10))])
def test_database_refuses_end_not_after_start(sign_up_owner, start, end):
    _, business_id = sign_up_owner()
    with pytest.raises(IntegrityError, match="ck_working_hours_end_after_start"):
        insert(hours(business_id, start=start, end=end))


@pytest.mark.parametrize("weekday", [-1, 7])
def test_database_refuses_bad_weekday(sign_up_owner, weekday):
    _, business_id = sign_up_owner()
    with pytest.raises(IntegrityError, match="ck_working_hours_weekday_valid"):
        insert(hours(business_id, weekday=weekday))


def test_database_refuses_two_rows_for_one_weekday(sign_up_owner):
    _, business_id = sign_up_owner()
    insert(hours(business_id, weekday=2))
    with pytest.raises(IntegrityError, match="uq_working_hours_business_id_weekday"):
        insert(hours(business_id, weekday=2))


def test_database_refuses_same_closed_day_twice(sign_up_owner):
    _, business_id = sign_up_owner()
    insert(ClosedDay(business_id=business_id, day=date(2026, 12, 25)))
    with pytest.raises(IntegrityError, match="uq_closed_days_business_id_day"):
        insert(ClosedDay(business_id=business_id, day=date(2026, 12, 25)))


def test_two_businesses_may_close_the_same_day(sign_up_owner):
    _, a = sign_up_owner()
    _, b = sign_up_owner()
    insert(ClosedDay(business_id=a, day=date(2026, 12, 25)), ClosedDay(business_id=b, day=date(2026, 12, 25)))

# Integration tests: Settings → Working Hours API (story 3.2, FR-10, FR-13, AR-5).
# The Owner sets the weekly hours (one range per open day) and closed dates. Every rule
# answers 422 with the message next to its field (UX-DR33), e.g. "tuesday.end_time".
# Staff and Technicians get 403 on every route.
import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.integration.conftest import assert_not_found

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.modules.business import service as business_service
from app.modules.business.models import Business, ClosedDay, WorkingHours
from app.modules.business.schemas import OpenHours

FORBIDDEN_BODY = {"error": {"code": "forbidden", "message": "You don't have access to this."}}
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
OPEN = {"start_time": "10:00", "end_time": "18:00"}
WEEK = {**{day: OPEN for day in DAYS[:6]}, "sunday": None}  # Mon–Sat 10–6, Sunday closed
SAVED = {"start_time": "10:00:00", "end_time": "18:00:00"}  # how the API sends a time back
BAD_TIME = "Use a time like 10:00."


def field_errors(response) -> dict[str, str]:
    """The 422 field errors as {field: message}."""
    assert response.status_code == 422, response.text
    return {item["field"]: item["message"] for item in response.json()["error"]["fields"]}


def get_week(client) -> dict:
    response = client.get("/api/v1/working-hours")
    assert response.status_code == 200, response.text
    return response.json()


def put_week(client, body: dict):
    return client.put("/api/v1/working-hours", json=body)


def save_week(client, body: dict = WEEK) -> dict:
    response = put_week(client, body)
    assert response.status_code == 200, response.text
    return response.json()


def row_count() -> int:
    with Session(get_engine()) as session:
        return session.scalar(select(func.count()).select_from(WorkingHours))


# ---------------------------------------------------------------- weekly hours


def test_new_business_has_no_hours(sign_up_owner):
    owner, _ = sign_up_owner()
    assert get_week(owner) == {"timezone": "Asia/Kolkata", **{day: None for day in DAYS}}


def test_owner_saves_week_and_reads_it_back(sign_up_owner):
    owner, _ = sign_up_owner()
    expected = {"timezone": "Asia/Kolkata", **{day: SAVED for day in DAYS[:6]}, "sunday": None}
    assert save_week(owner) == expected
    assert get_week(owner) == expected


def test_saving_again_replaces_the_week(sign_up_owner):
    owner, _ = sign_up_owner()
    save_week(owner)
    before = row_count()
    # The second save must not break the "one row per weekday" rule (no 500).
    week = save_week(owner, {**WEEK, "monday": None})
    assert week["monday"] is None
    assert row_count() == before - 1
    # What GET sends ("10:00:00") can be sent back unchanged.
    sent_back = {day: week[day] for day in DAYS}
    assert save_week(owner, sent_back) == week


@pytest.mark.parametrize(("start", "end"), [("10:00", "10:00"), ("18:00", "10:00")])
def test_end_not_after_start_is_refused_next_to_that_day(sign_up_owner, start, end):
    owner, _ = sign_up_owner()
    save_week(owner)
    response = put_week(owner, {**WEEK, "tuesday": {"start_time": start, "end_time": end}})
    assert field_errors(response) == {"tuesday.end_time": "End time must be after the start time."}
    assert get_week(owner)["tuesday"] == SAVED  # nothing saved


def test_missing_times_on_open_day(sign_up_owner):
    owner, _ = sign_up_owner()
    assert field_errors(put_week(owner, {**WEEK, "wednesday": {}})) == {
        "wednesday.start_time": "Enter a start time.",
        "wednesday.end_time": "Enter an end time.",
    }


@pytest.mark.parametrize("text", ["9:00", "24:00", "", "bad", "10:60", "10:00:30", "10:00:00.5", "10:00+05:30"])
def test_bad_time_refused(sign_up_owner, text):
    owner, _ = sign_up_owner()
    response = put_week(owner, {**WEEK, "monday": {"start_time": text, "end_time": "18:00"}})
    # Only the bad field: the end time is not compared with a start time that was refused.
    assert field_errors(response) == {"monday.start_time": BAD_TIME}


def test_missing_day_key_refused(sign_up_owner):
    owner, _ = sign_up_owner()
    body = {day: WEEK[day] for day in DAYS[:6]}  # no "sunday"
    assert "sunday" in field_errors(put_week(owner, body))


# ---------------------------------------------------------------- closed days

TODAY = date(2026, 12, 1)  # a Tuesday. Tests fix "today", so none can flip at midnight IST.


@pytest.fixture
def fixed_today(monkeypatch):
    monkeypatch.setattr(business_service, "_today", lambda business: TODAY)


def closed_days(client) -> list[dict]:
    response = client.get("/api/v1/closed-days")
    assert response.status_code == 200, response.text
    return response.json()["closed_days"]


def post_day(client, day):
    return client.post("/api/v1/closed-days", json={"day": day})


def close(client, day: str) -> dict:
    response = post_day(client, day)
    assert response.status_code == 201, response.text
    return response.json()


def test_owner_adds_lists_and_removes_closed_day(sign_up_owner, fixed_today):
    owner, _ = sign_up_owner()
    created = close(owner, "2026-12-25")
    assert created["day"] == "2026-12-25"
    assert closed_days(owner) == [created]
    response = owner.delete(f"/api/v1/closed-days/{created['closed_day_id']}")
    assert response.status_code == 204, response.text
    assert closed_days(owner) == []


def test_past_closed_day_refused(sign_up_owner, fixed_today):
    owner, _ = sign_up_owner()
    assert field_errors(post_day(owner, "2026-11-30")) == {"day": "Pick today or a later date."}
    close(owner, "2026-12-01")  # today itself is allowed


def test_past_rows_are_not_listed(sign_up_owner, fixed_today):
    owner, business_id = sign_up_owner()
    with Session(get_engine()) as session, session.begin():  # past the API, which refuses past dates
        session.add(ClosedDay(business_id=business_id, day=date(2026, 11, 20)))
    future = close(owner, "2026-12-25")
    assert closed_days(owner) == [future]


def test_duplicate_closed_day_refused(sign_up_owner, fixed_today):
    owner, _ = sign_up_owner()
    close(owner, "2026-12-25")
    assert field_errors(post_day(owner, "2026-12-25")) == {"day": "This date is already closed."}
    assert len(closed_days(owner)) == 1


@pytest.mark.parametrize(
    "body", [{}, {"day": None}, {"day": ""}, {"day": "2026-12-25T00:00"}, {"day": "2026-02-30"}, {"day": "25-12-2026"}]
)
def test_bad_closed_day_refused(sign_up_owner, fixed_today, body):
    owner, _ = sign_up_owner()
    assert field_errors(owner.post("/api/v1/closed-days", json=body)) == {"day": "Pick a date."}


def test_closed_days_listed_soonest_first(sign_up_owner, fixed_today):
    owner, _ = sign_up_owner()
    for day in ("2026-12-31", "2026-12-02", "2026-12-25"):
        close(owner, day)
    assert [row["day"] for row in closed_days(owner)] == ["2026-12-02", "2026-12-25", "2026-12-31"]


def test_today_uses_business_timezone():
    # A unit check of the one "today" helper (no monkeypatch here).
    business = Business(name="Test Shop", timezone="Asia/Kolkata")
    assert business_service._today(business) == datetime.now(ZoneInfo("Asia/Kolkata")).date()


def test_removing_a_closed_day_opens_the_date_again(sign_up_owner, fixed_today):
    owner, business_id = sign_up_owner()
    save_week(owner)  # Mon–Sat 10–6
    monday = date(2026, 12, 7)

    def hours_on(day: date) -> OpenHours | None:
        with Session(get_engine()) as session, tenant_scope(business_id):
            return business_service.hours_on(session, day)

    created = close(owner, "2026-12-07")
    assert hours_on(monday) is None

    response = owner.delete(f"/api/v1/closed-days/{created['closed_day_id']}")
    assert response.status_code == 204

    assert hours_on(monday) == OpenHours(start_time=time(10), end_time=time(18))


def test_hours_on_uses_weekly_hours_and_closed_days(sign_up_owner, fixed_today):
    owner, business_id = sign_up_owner()
    save_week(owner)  # Mon–Sat 10–6, Sunday closed
    monday, sunday = date(2026, 12, 7), date(2026, 12, 6)

    def hours_on(day: date) -> OpenHours | None:
        with Session(get_engine()) as session, tenant_scope(business_id):
            return business_service.hours_on(session, day)

    assert hours_on(monday) == OpenHours(start_time=time(10), end_time=time(18))
    assert hours_on(sunday) is None  # a closed weekday
    close(owner, "2026-12-07")
    assert hours_on(monday) is None  # a closed date wins over the weekly hours


# ---------------------------------------------------------------- roles


@pytest.mark.parametrize("roles", [["staff"], ["technician"], ["staff", "technician"]])
def test_staff_and_technician_get_403_on_hours_routes(sign_up_owner, invite_member, roles, fixed_today):
    owner, _ = sign_up_owner()
    save_week(owner)
    created = close(owner, "2026-12-25")
    member = invite_member(owner, roles).client

    for response in (
        member.get("/api/v1/working-hours"),
        put_week(member, {**WEEK, "monday": None}),
        member.get("/api/v1/closed-days"),
        post_day(member, "2026-12-26"),
        member.delete(f"/api/v1/closed-days/{created['closed_day_id']}"),
    ):
        assert response.status_code == 403, response.text
        assert response.json() == FORBIDDEN_BODY
    assert get_week(owner)["monday"] == SAVED  # nothing changed
    assert closed_days(owner) == [created]


def test_role_check_runs_before_lookup(sign_up_owner, invite_member):
    # A missing id still answers 403, so a 403 never tells Staff whether a record exists.
    owner, _ = sign_up_owner()
    member = invite_member(owner, ["staff"]).client
    assert member.delete(f"/api/v1/closed-days/{uuid.uuid4()}").status_code == 403


def test_unknown_closed_day_id_is_404(sign_up_owner):
    owner, _ = sign_up_owner()
    assert_not_found(owner.delete(f"/api/v1/closed-days/{uuid.uuid4()}"))


def test_logged_out_caller_gets_401(make_client):
    stranger = make_client()
    assert stranger.get("/api/v1/working-hours").status_code == 401
    assert stranger.get("/api/v1/closed-days").status_code == 401


# ---------------------------------------------------------------- review fixes (regression tests)


@pytest.mark.parametrize("value", [10, 10.5, True, ["10:00"], "1\u0660:00"])
def test_non_text_or_non_ascii_time_gets_our_message(sign_up_owner, value):
    # A JSON number, or digits from another script ("1٠:00"), must not leak Pydantic's text.
    owner, _ = sign_up_owner()
    response = put_week(owner, {**WEEK, "monday": {"start_time": value, "end_time": "18:00"}})
    assert field_errors(response) == {"monday.start_time": BAD_TIME}


@pytest.mark.parametrize("value", [20261225, True, "2026-1\u0662-25"])
def test_non_text_or_non_ascii_date_gets_our_message(sign_up_owner, fixed_today, value):
    owner, _ = sign_up_owner()
    assert field_errors(post_day(owner, value)) == {"day": "Pick a date."}


def test_input_schemas_hold_real_times_and_dates():
    # The declared types match the values: no serializer warnings, no strings in disguise.
    import warnings

    from app.modules.business.schemas import ClosedDayIn, DayIn

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        day = DayIn(start_time="10:00", end_time="18:00")
        assert day.model_dump() == {"start_time": time(10), "end_time": time(18)}
        assert ClosedDayIn(day="2026-12-25").model_dump() == {"day": date(2026, 12, 25)}

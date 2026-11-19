# Integration tests: Settings → Working Hours API (story 3.2, FR-10, FR-13, AR-5).
# The Owner sets the weekly hours (one range per open day) and closed dates. Every rule
# answers 422 with the message next to its field (UX-DR33), e.g. "tuesday.end_time".
# Staff and Technicians get 403 on every route.
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.modules.business.models import WorkingHours

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


@pytest.mark.parametrize("roles", [["staff"], ["technician"], ["staff", "technician"]])
def test_staff_and_technician_get_403_on_hours_routes(sign_up_owner, invite_member, roles):
    owner, _ = sign_up_owner()
    save_week(owner)
    member = invite_member(owner, roles).client

    for response in (member.get("/api/v1/working-hours"), put_week(member, {**WEEK, "monday": None})):
        assert response.status_code == 403, response.text
        assert response.json() == FORBIDDEN_BODY
    assert get_week(owner)["monday"] == SAVED  # nothing changed


def test_logged_out_caller_gets_401(make_client):
    stranger = make_client()
    assert stranger.get("/api/v1/working-hours").status_code == 401

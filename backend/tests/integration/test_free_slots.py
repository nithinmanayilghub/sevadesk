# Integration tests: free Slots from real rows (story 5.1, FR-17, AR-14).
# The shop and the fixed clock: see booking_helpers.py.
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session
from tests.integration.booking_helpers import HOUR, MON_10, NOW, TZ, book, fixed_clock, make_shop
from tests.integration.conftest import membership_of, set_owner_roles
from tests.integration.test_tenant_isolation import SERVICE

from app.core.db import get_engine
from app.core.errors import NotFound
from app.core.tenancy import tenant_scope
from app.modules.accounts.schemas import Actor, Role
from app.modules.bookings import service as bookings_service

pytestmark = pytest.mark.usefixtures("fixed_clock")
__all__ = ["fixed_clock"]  # imported so pytest can find the fixture by name


def _starts(business_id: uuid.UUID, service_id: uuid.UUID) -> list[datetime]:
    """The free Slot starts, on the shop's clock, from the bookings front door."""
    actor = Actor(
        user_id=uuid.uuid4(),
        membership_id=membership_of(business_id),
        business_id=business_id,
        roles={Role.OWNER, Role.TECHNICIAN},
    )
    with Session(get_engine()) as session, tenant_scope(business_id):
        result = bookings_service.list_free_slots(session, actor, service_id)
    assert result.timezone == "Asia/Kolkata"
    return [slot.start.astimezone(TZ) for slot in result.slots]


def test_expired_request_frees_capacity(sign_up_owner):
    _, business_id, service_id = make_shop(sign_up_owner)
    book(business_id, service_id, MON_10, "requested", expires_at=NOW - HOUR)
    assert MON_10 in _starts(business_id, service_id)  # expired: it no longer holds the Slot

    book(business_id, service_id, MON_10, "requested", expires_at=NOW + HOUR)
    assert MON_10 not in _starts(business_id, service_id)  # still waiting: it holds the Slot


def test_request_expiring_right_now_is_expired(sign_up_owner):
    # The edge: expires_at == now. "Live" needs expires_at > now, so it no longer holds the Slot.
    _, business_id, service_id = make_shop(sign_up_owner)
    book(business_id, service_id, MON_10, "requested", expires_at=NOW)
    assert MON_10 in _starts(business_id, service_id)


def test_confirmed_booking_takes_capacity(sign_up_owner):
    _, business_id, service_id = make_shop(sign_up_owner)
    book(business_id, service_id, MON_10, "confirmed")
    starts = _starts(business_id, service_id)
    assert MON_10 not in starts
    assert MON_10 + timedelta(minutes=30) not in starts  # 10:30-11:30 overlaps 10:00-11:00
    assert MON_10 + HOUR in starts  # 11:00 only touches it


def test_only_live_bookings_of_this_business_count(sign_up_owner):
    _, a_id, a_service = make_shop(sign_up_owner)
    _, b_id, b_service = make_shop(sign_up_owner)
    # A future expires_at on each, so only the STATE can make them not count (a rule that
    # looked only at expires_at would wrongly count them).
    for state in ("cancelled", "completed", "declined", "expired"):
        book(a_id, a_service, MON_10, state, expires_at=NOW + HOUR)
    book(b_id, b_service, MON_10, "confirmed")  # B's job takes B's Technician, not A's
    assert MON_10 in _starts(a_id, a_service)


def test_closed_day_has_no_slots(sign_up_owner):
    owner, business_id, service_id = make_shop(sign_up_owner)
    assert owner.post("/api/v1/closed-days", json={"day": "2026-12-01"}).status_code == 201
    days = {start.date() for start in _starts(business_id, service_id)}
    assert date(2026, 12, 1) not in days
    assert date(2026, 11, 30) in days


def test_window_is_seven_business_days(sign_up_owner):
    _, business_id, service_id = make_shop(sign_up_owner)
    days = {start.date() for start in _starts(business_id, service_id)}
    # Mon 30 Nov - Sat 5 Dec. Sun 6 Dec has no hours; Mon 7 Dec is the 8th day.
    assert days == {date(2026, 11, 30) + timedelta(days=offset) for offset in range(6)}


def test_window_starts_on_the_business_date_after_midnight(sign_up_owner, monkeypatch):
    # 19:00 UTC on Fri 4 Dec is already 00:30 on Sat 5 Dec in India. The window must be
    # Sat 5 - Fri 11 Dec. With the UTC date it would be Fri 4 - Thu 10, and lose Fri 11.
    monkeypatch.setattr(bookings_service, "_now", lambda: datetime(2026, 12, 4, 19, 0, tzinfo=UTC))
    _, business_id, service_id = make_shop(sign_up_owner)
    days = {start.date() for start in _starts(business_id, service_id)}
    assert min(days) == date(2026, 12, 5)
    assert max(days) == date(2026, 12, 11)


def test_inactive_service_is_not_found(sign_up_owner):
    owner, business_id, service_id = make_shop(sign_up_owner)
    changed = owner.put(f"/api/v1/services/{service_id}", json={**SERVICE, "is_active": False})
    assert changed.status_code == 200, changed.text
    with pytest.raises(NotFound):
        _starts(business_id, service_id)


# ---------------------------------------------------------------- the HTTP route (FR-10)

FORBIDDEN_BODY = {"error": {"code": "forbidden", "message": "You don't have access to this."}}


def _get_slots(client, service_id: uuid.UUID):
    return client.get("/api/v1/bookings/slots", params={"service_id": str(service_id)})


def test_owner_gets_free_slots(sign_up_owner):
    owner, _, service_id = make_shop(sign_up_owner)
    response = _get_slots(owner, service_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["timezone"] == "Asia/Kolkata"
    assert body["slots"][0] == {"start": "2026-11-30T04:30:00Z", "end": "2026-11-30T05:30:00Z"}  # Mon 10-11 IST


def test_staff_gets_free_slots(sign_up_owner):
    owner, business_id, service_id = make_shop(sign_up_owner)
    set_owner_roles(business_id, ["staff"])  # the only member is now Staff: no Technician left
    response = _get_slots(owner, service_id)
    assert response.status_code == 200, response.text
    assert response.json()["slots"] == []  # nobody can do the job, so no time is free


def test_technician_only_gets_403(sign_up_owner):
    owner, business_id, service_id = make_shop(sign_up_owner)
    set_owner_roles(business_id, ["technician"])
    response = _get_slots(owner, service_id)
    assert response.status_code == 403
    assert response.json() == FORBIDDEN_BODY


def test_logged_out_gets_401(make_client):
    assert _get_slots(make_client(), uuid.uuid4()).status_code == 401

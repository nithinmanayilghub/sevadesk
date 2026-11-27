# Integration tests: free Slots from real rows (story 5.1, FR-17, AR-14).
# The shop: one Owner (who is also the one Technician), a 60-min Service, open Mon-Sat 10:00-18:00
# in India. "Now" is fixed at Mon 30 Nov 2026 00:00 IST, so the 7-day window is Mon 30 Nov - Sun 6 Dec.
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session
from tests.integration.conftest import membership_of
from tests.integration.test_tenant_isolation import HOURS_WEEK, SERVICE

from app.core.db import get_engine
from app.core.errors import NotFound
from app.core.tenancy import tenant_scope
from app.modules.accounts.schemas import Actor, Role
from app.modules.bookings import service as bookings_service
from app.modules.bookings.models import Booking
from app.modules.business import service as business_service
from app.modules.inbox.models import Customer

TZ = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 29, 18, 30, tzinfo=UTC)  # = Mon 30 Nov 00:00 in India
MON_10 = datetime(2026, 11, 30, 10, 0, tzinfo=TZ)
HOUR = timedelta(hours=1)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    # The one clock of bookings, and "today" of business (closed days refuse past dates).
    monkeypatch.setattr(bookings_service, "_now", lambda: NOW)
    monkeypatch.setattr(business_service, "_today", lambda business: NOW.astimezone(TZ).date())


def _shop(sign_up_owner):
    """A ready shop. Returns (owner client, business_id, service_id)."""
    owner, business_id = sign_up_owner()
    service = owner.post("/api/v1/services", json=SERVICE)
    assert service.status_code == 201, service.text
    assert owner.put("/api/v1/working-hours", json=HOURS_WEEK).status_code == 200
    return owner, business_id, uuid.UUID(service.json()["service_id"])


def _book(business_id: uuid.UUID, start: datetime, state: str, expires_at: datetime | None = None) -> None:
    """Save a one-hour Booking straight into the database (no booking API exists yet)."""
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        customer = Customer(id=uuid.uuid7(), business_id=business_id)
        session.add(customer)
        session.flush()
        session.add(
            Booking(
                business_id=business_id,
                state=state,
                starts_at=start,
                ends_at=start + HOUR,
                customer_id=customer.id,
                technician_membership_id=None if state in ("requested", "declined") else membership_of(business_id),
                price_paise=49900,
                expires_at=expires_at,
            )
        )


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
    _, business_id, service_id = _shop(sign_up_owner)
    _book(business_id, MON_10, "requested", expires_at=NOW - HOUR)
    assert MON_10 in _starts(business_id, service_id)  # expired: it no longer holds the Slot

    _book(business_id, MON_10, "requested", expires_at=NOW + HOUR)
    assert MON_10 not in _starts(business_id, service_id)  # still waiting: it holds the Slot


def test_confirmed_booking_takes_capacity(sign_up_owner):
    _, business_id, service_id = _shop(sign_up_owner)
    _book(business_id, MON_10, "confirmed")
    starts = _starts(business_id, service_id)
    assert MON_10 not in starts
    assert MON_10 + timedelta(minutes=30) not in starts  # 10:30-11:30 overlaps 10:00-11:00
    assert MON_10 + HOUR in starts  # 11:00 only touches it


def test_only_live_bookings_of_this_business_count(sign_up_owner):
    _, a_id, a_service = _shop(sign_up_owner)
    _, b_id, _ = _shop(sign_up_owner)
    for state in ("cancelled", "completed", "declined"):
        _book(a_id, MON_10, state)
    _book(b_id, MON_10, "confirmed")  # B's job takes B's Technician, not A's
    assert MON_10 in _starts(a_id, a_service)


def test_closed_day_has_no_slots(sign_up_owner):
    owner, business_id, service_id = _shop(sign_up_owner)
    assert owner.post("/api/v1/closed-days", json={"day": "2026-12-01"}).status_code == 201
    days = {start.date() for start in _starts(business_id, service_id)}
    assert date(2026, 12, 1) not in days
    assert date(2026, 11, 30) in days


def test_window_is_seven_business_days(sign_up_owner):
    _, business_id, service_id = _shop(sign_up_owner)
    days = {start.date() for start in _starts(business_id, service_id)}
    # Mon 30 Nov - Sat 5 Dec. Sun 6 Dec has no hours; Mon 7 Dec is the 8th day.
    assert days == {date(2026, 11, 30) + timedelta(days=offset) for offset in range(6)}


def test_inactive_service_is_not_found(sign_up_owner):
    owner, business_id, service_id = _shop(sign_up_owner)
    changed = owner.put(f"/api/v1/services/{service_id}", json={**SERVICE, "is_active": False})
    assert changed.status_code == 200, changed.text
    with pytest.raises(NotFound):
        _starts(business_id, service_id)

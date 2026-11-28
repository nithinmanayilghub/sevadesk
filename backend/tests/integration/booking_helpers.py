# Shared helpers for the bookings tests (stories 5.1 and 5.2).
# The shop: one Owner (who is also the one Technician), a 60-min Service, open Mon-Sat 10:00-18:00
# in India. "Now" is fixed at Mon 30 Nov 2026 00:00 IST, so the 7-day window is Mon 30 Nov - Sun 6 Dec.
#
# A test file that needs the fixed clock imports `fixed_clock` and marks itself with
# pytestmark = pytest.mark.usefixtures("fixed_clock"). Without it, "now" is the real clock,
# and MON_10 becomes the past after 30 Nov 2026.
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.conftest import membership_of
from tests.integration.test_tenant_isolation import HOURS_WEEK, SERVICE

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.modules.accounts.models import Membership
from app.modules.accounts.schemas import Actor
from app.modules.bookings import service as bookings_service
from app.modules.bookings.models import Booking
from app.modules.business import service as business_service
from app.modules.inbox.models import Customer

TZ = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 29, 18, 30, tzinfo=UTC)  # = Mon 30 Nov 00:00 in India
MON_10 = datetime(2026, 11, 30, 10, 0, tzinfo=TZ)
HOUR = timedelta(hours=1)

# States that never have a Technician in these tests (a request gets one only on confirm).
_NO_TECHNICIAN = ("requested", "declined", "expired")


@pytest.fixture
def fixed_clock(monkeypatch):
    # The one clock of bookings, and "today" of business (closed days refuse past dates).
    monkeypatch.setattr(bookings_service, "_now", lambda: NOW)
    monkeypatch.setattr(business_service, "_today", lambda business: NOW.astimezone(TZ).date())


def make_shop(sign_up_owner):
    """A ready shop. Returns (owner client, business_id, service_id)."""
    owner, business_id = sign_up_owner()
    service = owner.post("/api/v1/services", json=SERVICE)
    assert service.status_code == 201, service.text
    assert owner.put("/api/v1/working-hours", json=HOURS_WEEK).status_code == 200
    return owner, business_id, uuid.UUID(service.json()["service_id"])


def new_customer(business_id: uuid.UUID) -> uuid.UUID:
    """A chat-style Customer (no name, no phone), saved and committed. Returns its id."""
    customer_id = uuid.uuid7()
    with Session(get_engine()) as session, session.begin():
        session.add(Customer(id=customer_id, business_id=business_id))
    return customer_id


def book(
    business_id: uuid.UUID,
    service_id: uuid.UUID,
    start: datetime,
    state: str,
    *,
    technician_id: uuid.UUID | None = None,
    expires_at: datetime | None = None,
) -> uuid.UUID:
    """Save a one-hour Booking straight into the database, past the API. Returns its id.

    technician_id: leave it out in a ONE-member shop, and a confirmed-like Booking gets the
    Owner (membership_of works only while the Business has one member). With 2+ members, pass it.
    """
    if technician_id is None and state not in _NO_TECHNICIAN:
        technician_id = membership_of(business_id)
    customer_id = new_customer(business_id)
    booking_id = uuid.uuid7()
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        session.add(
            Booking(
                id=booking_id,
                business_id=business_id,
                state=state,
                starts_at=start,
                ends_at=start + HOUR,
                customer_id=customer_id,
                service_id=service_id,
                technician_membership_id=technician_id,
                price_paise=49900,
                expires_at=expires_at,
            )
        )
    return booking_id


def owner_actor(business_id: uuid.UUID) -> Actor:
    """The Owner of this Business as an Actor. Works with 2+ members too (found by Role)."""
    with Session(get_engine()) as session:
        query = select(Membership).where(Membership.business_id == business_id, Membership.roles.contains(["owner"]))
        membership = session.scalars(query).one()
    return Actor(
        user_id=membership.user_id,
        membership_id=membership.id,
        business_id=business_id,
        roles=set(membership.roles),
    )

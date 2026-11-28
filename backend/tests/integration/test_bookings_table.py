# Database guards of the bookings table (story 5.1, AR-6, AD-9).
# Each test writes rows straight into Postgres, inside one transaction that is rolled back,
# so the database rules themselves are tested (not the API in front of them).
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.modules.accounts.models import Membership
from app.modules.accounts.repository import MembershipRepository, UserRepository
from app.modules.bookings.models import Booking
from app.modules.business.models import Service
from app.modules.business.repository import BusinessRepository
from app.modules.inbox.models import Conversation, Customer, VisitorToken

pytestmark = pytest.mark.isolation

START = datetime(2026, 11, 30, 4, 30, tzinfo=UTC)  # Mon 30 Nov, 10:00 in India
END = START + timedelta(hours=1)


@dataclass
class Tenant:
    business_id: uuid.UUID
    membership_id: uuid.UUID
    customer_id: uuid.UUID
    conversation_id: uuid.UUID
    service_id: uuid.UUID


def _tenant(session: Session, name: str) -> Tenant:
    """One Business with one member (a Technician), one Service, one Customer, and their Conversation."""
    business = BusinessRepository(session).add(name)
    user = UserRepository(session).add(f"{uuid.uuid4().hex}@example.com", "not-a-real-hash")
    with tenant_scope(business.id):
        membership = MembershipRepository(session).add(Membership(user_id=user.id, roles=["technician"]))
        customer = Customer(id=uuid.uuid7(), business_id=business.id)
        token = VisitorToken(id=uuid.uuid7(), business_id=business.id, token_hash=uuid.uuid4().hex)
        service = Service(
            id=uuid.uuid7(), business_id=business.id, name="AC gas check", duration_minutes=60, price_paise=49900
        )
        session.add_all([customer, token, service])
        session.flush()
        conversation = Conversation(
            id=uuid.uuid7(), business_id=business.id, customer_id=customer.id, visitor_token_id=token.id
        )
        session.add(conversation)
        session.flush()
    return Tenant(business.id, membership.id, customer.id, conversation.id, service.id)


@pytest.fixture
def db(migrated_db):
    """A session inside one transaction that is rolled back at the end, plus Businesses A and B."""
    with get_engine().connect() as conn, conn.begin() as tx:
        session = Session(bind=conn)
        yield session, _tenant(session, "A"), _tenant(session, "B")
        session.close()
        tx.rollback()


def _booking(tenant: Tenant, **changes) -> Booking:
    """A good confirmed Booking of this tenant; `changes` breaks one field on purpose."""
    fields = {
        "id": uuid.uuid7(),
        "business_id": tenant.business_id,
        "state": "confirmed",
        "starts_at": START,
        "ends_at": END,
        "customer_id": tenant.customer_id,
        "conversation_id": tenant.conversation_id,
        "technician_membership_id": tenant.membership_id,
        "service_id": tenant.service_id,
        "price_paise": 49900,
    }
    return Booking(**(fields | changes))


def _refused(session: Session, row: Booking) -> None:
    """The database must refuse this row. A savepoint keeps the outer transaction usable."""
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(row)
        session.flush()


def test_booking_row_saves(db):
    session, a, _ = db
    row = _booking(a)
    session.add(row)
    session.flush()
    assert session.get(Booking, row.id).state == "confirmed"


def test_customer_of_another_business_is_refused(db):
    session, a, b = db
    _refused(session, _booking(a, customer_id=b.customer_id))


def test_conversation_of_another_business_is_refused(db):
    session, a, b = db
    _refused(session, _booking(a, conversation_id=b.conversation_id))


def test_technician_of_another_business_is_refused(db):
    session, a, b = db
    _refused(session, _booking(a, technician_membership_id=b.membership_id))


def test_requested_needs_expiry(db):
    session, a, _ = db
    _refused(session, _booking(a, state="requested", technician_membership_id=None, expires_at=None))


def test_confirmed_needs_technician(db):
    session, a, _ = db
    _refused(session, _booking(a, technician_membership_id=None))


def test_end_must_be_after_start(db):
    session, a, _ = db
    _refused(session, _booking(a, ends_at=START))


def test_booking_needs_a_service(db):
    session, a, _ = db
    _refused(session, _booking(a, service_id=None))


def test_booking_cannot_point_at_another_business_service(db):
    session, a, b = db
    _refused(session, _booking(a, service_id=b.service_id))

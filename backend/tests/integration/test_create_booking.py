# Integration tests: the one Booking write path, bookings.create_confirmed (story 5.2, AD-9, FR-27).
# They call the front door directly, inside a tenant scope, like the free-Slot tests.
# The shop and the fixed clock: see booking_helpers.py.
import uuid
from datetime import datetime, timedelta

import pytest
from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.booking_helpers import (
    HOUR,
    MON_10,
    NOW,
    book,
    fixed_clock,
    make_shop,
    new_customer,
    owner_actor,
)
from tests.integration.test_team_manage import patch

from app.core.db import get_engine
from app.core.errors import AppError, Forbidden, NotFound
from app.core.tenancy import tenant_scope
from app.modules.accounts.schemas import Actor, Role
from app.modules.bookings import service as bookings_service
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import BookingOut, NewBooking
from app.modules.bookings.service import SlotUnavailable, TechnicianBusy

pytestmark = pytest.mark.usefixtures("fixed_clock")
__all__ = ["fixed_clock"]  # imported so pytest can find the fixture by name


def _create(
    business_id: uuid.UUID,
    service_id: uuid.UUID,
    start: datetime,
    *,
    technician_id: uuid.UUID | None = None,
    actor: Actor | None = None,
) -> BookingOut:
    """Call the front door in its own committed transaction, like one request would."""
    data = NewBooking(
        customer_id=new_customer(business_id),
        conversation_id=None,
        service_id=service_id,
        starts_at=start,
        technician_membership_id=technician_id,
    )
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        return bookings_service.create_confirmed(session, actor or owner_actor(business_id), data)


def _free_starts(business_id: uuid.UUID, service_id: uuid.UUID) -> list[datetime]:
    with Session(get_engine()) as session, tenant_scope(business_id):
        result = bookings_service.list_free_slots(session, owner_actor(business_id), service_id)
    return [slot.start for slot in result.slots]


def _bookings(business_id: uuid.UUID) -> list[Booking]:
    with Session(get_engine()) as session:
        return list(session.scalars(select(Booking).where(Booking.business_id == business_id)))


def _two_technicians(sign_up_owner, invite_member):
    """A shop where the Owner AND an invited member are Technicians. Returns (owner, business, service, member)."""
    owner, business_id, service_id = make_shop(sign_up_owner)
    member = invite_member(owner, ["technician"])
    return owner, business_id, service_id, member


def test_saves_a_confirmed_booking(sign_up_owner):
    # Behaviour: a free Slot becomes a confirmed Booking with the Service's Price and length.
    _, business_id, service_id = make_shop(sign_up_owner)
    owner = owner_actor(business_id)
    booking = _create(business_id, service_id, MON_10)
    assert booking.state == "confirmed"
    assert booking.technician_membership_id == owner.membership_id  # the only Technician
    assert booking.starts_at == MON_10
    assert booking.ends_at == MON_10 + HOUR
    assert booking.price_paise == 49900
    assert booking.service_id == service_id
    assert booking.conversation_id is None
    assert MON_10 not in _free_starts(business_id, service_id)  # the Slot is taken now


def test_booking_created_trace_event(sign_up_owner, spans):
    # Behaviour: a new Booking leaves a note in the trace, with no ids, name, or phone (AD-13).
    _, business_id, service_id = make_shop(sign_up_owner)
    spans.clear()
    with trace.get_tracer(__name__).start_as_current_span("test request"):  # stands in for the request span
        _create(business_id, service_id, MON_10)
    events = [e for s in spans.finished() for e in s.events if e.name == "booking.created"]
    assert [dict(e.attributes) for e in events] == [{"state": "confirmed", "from_conversation": False}]


def test_full_slot_is_unavailable(sign_up_owner):
    # Behaviour: the recount sees the confirmed job, so the only Technician is not free.
    _, business_id, service_id = make_shop(sign_up_owner)
    book(business_id, service_id, MON_10, "confirmed")
    with pytest.raises(SlotUnavailable):
        _create(business_id, service_id, MON_10)


def test_live_request_takes_capacity(sign_up_owner):
    # Behaviour: a Booking Request that has not expired also holds the Slot (AD-9).
    _, business_id, service_id = make_shop(sign_up_owner)
    book(business_id, service_id, MON_10, "requested", expires_at=NOW + HOUR)
    with pytest.raises(SlotUnavailable):
        _create(business_id, service_id, MON_10)


@pytest.mark.parametrize(
    "start",
    [
        MON_10 + timedelta(minutes=10),  # off the 30-minute grid
        MON_10 + timedelta(days=6),  # Sunday: no Working Hours
        MON_10 - timedelta(days=2),  # before now
        MON_10 + timedelta(days=8),  # past the 7-day window
    ],
)
def test_time_off_the_grid_is_unavailable(sign_up_owner, start):
    # Behaviour: only a time the Slot list would show can be booked; nothing is saved.
    _, business_id, service_id = make_shop(sign_up_owner)
    with pytest.raises(SlotUnavailable):
        _create(business_id, service_id, start)
    assert _bookings(business_id) == []


def test_two_technicians_need_a_pick(sign_up_owner, invite_member):
    # Behaviour: with 2 Technicians, we never guess who goes: the caller must pick (FR-25).
    _, business_id, service_id, _ = _two_technicians(sign_up_owner, invite_member)
    with pytest.raises(AppError) as error:
        _create(business_id, service_id, MON_10)
    assert error.value.status_code == 422
    assert [(f.field, f.message) for f in error.value.fields] == [("technician_membership_id", "Pick a Technician.")]


def test_picked_technician_is_saved(sign_up_owner, invite_member):
    # Behaviour: with 2 Technicians, the picked one gets the job.
    _, business_id, service_id, member = _two_technicians(sign_up_owner, invite_member)
    booking = _create(business_id, service_id, MON_10, technician_id=member.membership_id)
    assert booking.technician_membership_id == member.membership_id


def test_inactive_technician_is_refused(sign_up_owner, invite_member):
    # Behaviour: a deactivated member cannot be given a job.
    owner, business_id, service_id, member = _two_technicians(sign_up_owner, invite_member)
    assert patch(owner, member.membership_id, {"is_active": False}).status_code == 200
    with pytest.raises(AppError) as error:
        _create(business_id, service_id, MON_10, technician_id=member.membership_id)
    assert error.value.status_code == 422
    assert [(f.field, f.message) for f in error.value.fields] == [
        ("technician_membership_id", "Pick an active Technician.")
    ]


def test_busy_technician_is_refused(sign_up_owner, invite_member):
    # Behaviour: one Technician does one job at a time, even when the shop still has room.
    _, business_id, service_id, member = _two_technicians(sign_up_owner, invite_member)
    book(business_id, service_id, MON_10, "confirmed", technician_id=member.membership_id)
    with pytest.raises(TechnicianBusy):
        _create(business_id, service_id, MON_10, technician_id=member.membership_id)


def test_technician_only_user_is_forbidden(sign_up_owner):
    # Behaviour: a Technician-only User may not book (FR-10). Checked before anything is read.
    _, business_id, service_id = make_shop(sign_up_owner)
    actor = owner_actor(business_id).model_copy(update={"roles": {Role.TECHNICIAN}})
    with pytest.raises(Forbidden):
        _create(business_id, service_id, MON_10, actor=actor)


def test_other_business_service_is_not_found(sign_up_owner):
    # Behaviour: another Business's Service looks like a missing one (FR-11).
    _, business_id, _ = make_shop(sign_up_owner)
    _, _, other_service = make_shop(sign_up_owner)
    with pytest.raises(NotFound):
        _create(business_id, other_service, MON_10)

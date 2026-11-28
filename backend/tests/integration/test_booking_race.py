# The race for the last free Slot (story 5.2, AD-9, AR-14).
# Two transactions book the same Slot at the same moment. Without a lock, both recounts see
# "free" and both save: a double booking. With the per-Business capacity lock, the second one
# WAITS until the first commits, then its recount sees the new Booking and says SlotUnavailable.
#
# How the test makes "the same moment" happen on purpose (not by luck):
# 1. Session 1 books and does NOT commit yet (it holds the lock, if there is one).
# 2. A thread starts session 2 for the same Slot.
# 3. We check that the thread is still running: it must be waiting for the lock.
# 4. Session 1 commits; the thread goes on and finishes.
import threading
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.booking_helpers import MON_10, fixed_clock, make_shop, new_customer, owner_actor

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.modules.bookings import service as bookings_service
from app.modules.bookings.models import Booking
from app.modules.bookings.schemas import NewBooking
from app.modules.bookings.service import SlotUnavailable

pytestmark = pytest.mark.usefixtures("fixed_clock")
__all__ = ["fixed_clock"]  # imported so pytest can find the fixture by name


def _new_booking(business_id: uuid.UUID, service_id: uuid.UUID) -> NewBooking:
    # The Customer is made and COMMITTED first, so the race is only about the Booking.
    return NewBooking(
        customer_id=new_customer(business_id),
        conversation_id=None,
        service_id=service_id,
        starts_at=MON_10,
        technician_membership_id=None,
    )


def _book_in_thread(business_id: uuid.UUID, data: NewBooking, result: dict) -> threading.Thread:
    """Start session 2 in its own thread. Leaving the `with` commits a success."""

    def run() -> None:
        try:
            # tenant_scope inside the thread: context variables do not cross threads.
            with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
                result["booking"] = bookings_service.create_confirmed(session, owner_actor(business_id), data)
        except BaseException as error:  # noqa: BLE001 - checked by the asserts
            result["error"] = error

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def _confirmed_at_mon_10(business_id: uuid.UUID) -> int:
    with Session(get_engine()) as session:
        query = select(Booking).where(Booking.business_id == business_id, Booking.starts_at == MON_10)
        return len(session.scalars(query).all())


def test_two_people_book_the_last_slot_one_wins(sign_up_owner):
    # Behaviour: two bookings of the last free Slot at once -> exactly one wins, one gets SlotUnavailable.
    _, business_id, service_id = make_shop(sign_up_owner)  # one Technician: MON_10 has room for 1 job
    first_data, second_data = _new_booking(business_id, service_id), _new_booking(business_id, service_id)
    result: dict = {}

    with Session(get_engine()) as first, tenant_scope(business_id):
        first.begin()
        bookings_service.create_confirmed(first, owner_actor(business_id), first_data)  # not committed yet
        thread = _book_in_thread(business_id, second_data, result)
        thread.join(timeout=1)
        waited = thread.is_alive()  # still running = waiting for session 1's lock
        first.commit()
    thread.join(timeout=10)

    assert not thread.is_alive(), "session 2 never finished"
    assert waited, "session 2 did not wait for session 1: there is no capacity lock"
    assert isinstance(result.get("error"), SlotUnavailable), result
    assert _confirmed_at_mon_10(business_id) == 1


def test_lock_is_per_business(sign_up_owner):
    # Behaviour: Business A's booking never makes Business B wait: the lock key is the Business.
    _, a_id, a_service = make_shop(sign_up_owner)
    _, b_id, b_service = make_shop(sign_up_owner)
    a_data, b_data = _new_booking(a_id, a_service), _new_booking(b_id, b_service)
    result: dict = {}

    with Session(get_engine()) as first, tenant_scope(a_id):
        first.begin()
        bookings_service.create_confirmed(first, owner_actor(a_id), a_data)  # A holds A's lock
        thread = _book_in_thread(b_id, b_data, result)
        thread.join(timeout=2)
        finished_while_a_was_open = not thread.is_alive()
        first.commit()
    thread.join(timeout=10)

    assert finished_while_a_was_open, "Business B waited for Business A's lock"
    assert "booking" in result, result
    assert _confirmed_at_mon_10(a_id) == 1
    assert _confirmed_at_mon_10(b_id) == 1

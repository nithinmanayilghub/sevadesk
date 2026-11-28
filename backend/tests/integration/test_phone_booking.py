# Integration tests: the two inbox flows that make a Booking (story 5.2, FR-27, UJ-2).
# - POST /api/v1/inbox/phone-bookings: a Customer who phoned (found or made by phone).
# - POST /api/v1/inbox/conversations/{id}/bookings: from an open Conversation.
# The shop and the fixed clock: see booking_helpers.py.
import threading
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.booking_helpers import HOUR, MON_10, fixed_clock, make_shop, owner_actor
from tests.integration.conftest import set_owner_roles
from tests.integration.test_inbox_list import new_chat

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.modules.bookings.models import Booking
from app.modules.inbox import service as inbox_service
from app.modules.inbox.models import Conversation, Customer
from app.modules.inbox.schemas import PhoneBookingIn

pytestmark = pytest.mark.usefixtures("fixed_clock")
__all__ = ["fixed_clock"]  # imported so pytest can find the fixture by name

PHONE_URL = "/api/v1/inbox/phone-bookings"
PHONE = "98765 43210"


def chat_url(conversation_id) -> str:
    return f"/api/v1/inbox/conversations/{conversation_id}/bookings"


def phone_body(service_id: uuid.UUID, start=MON_10, **changes) -> dict:
    body = {
        "customer_name": "Asha",
        "customer_phone": PHONE,
        "service_id": str(service_id),
        "starts_at": start.isoformat(),
    }
    return body | changes


def customers(business_id: uuid.UUID) -> list[Customer]:
    with Session(get_engine()) as session:
        return list(session.scalars(select(Customer).where(Customer.business_id == business_id)))


def bookings(business_id: uuid.UUID) -> list[Booking]:
    with Session(get_engine()) as session:
        return list(session.scalars(select(Booking).where(Booking.business_id == business_id)))


def test_phone_in_booking_is_confirmed_without_conversation(sign_up_owner):
    # Behaviour: a phone-in Booking is confirmed at once, has no Conversation, and a new Customer.
    owner, business_id, service_id = make_shop(sign_up_owner)
    response = owner.post(PHONE_URL, json=phone_body(service_id))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "confirmed"
    assert body["conversation_id"] is None
    assert body["starts_at"] == "2026-11-30T04:30:00Z"
    (customer,) = customers(business_id)
    assert (customer.id, customer.name, customer.phone) == (uuid.UUID(body["customer_id"]), "Asha", "+919876543210")


def test_phone_formats_find_one_customer(sign_up_owner):
    # Behaviour: one phone typed two ways is ONE Customer (the PRD: known by phone).
    owner, business_id, service_id = make_shop(sign_up_owner)
    first = owner.post(PHONE_URL, json=phone_body(service_id, customer_phone="98765 43210"))
    second = owner.post(PHONE_URL, json=phone_body(service_id, MON_10 + HOUR, customer_phone="+91-98765-43210"))
    assert (first.status_code, second.status_code) == (201, 201), second.text
    assert first.json()["customer_id"] == second.json()["customer_id"]
    assert len(customers(business_id)) == 1


def test_found_customer_keeps_its_name(sign_up_owner):
    # Behaviour: a found Customer is used as it is; a second call does not rename them.
    owner, business_id, service_id = make_shop(sign_up_owner)
    owner.post(PHONE_URL, json=phone_body(service_id))
    owner.post(PHONE_URL, json=phone_body(service_id, MON_10 + HOUR, customer_name="Someone else"))
    assert [customer.name for customer in customers(business_id)] == ["Asha"]


def test_second_identical_post_does_not_double_book(sign_up_owner):
    # Behaviour: a double tap on "Book" saves one Booking; the second gets a clear 409.
    owner, business_id, service_id = make_shop(sign_up_owner)
    assert owner.post(PHONE_URL, json=phone_body(service_id)).status_code == 201
    again = owner.post(PHONE_URL, json=phone_body(service_id))
    assert again.status_code == 409
    assert len(bookings(business_id)) == 1


def test_taken_slot_gives_409(sign_up_owner):
    owner, _, service_id = make_shop(sign_up_owner)
    owner.post(PHONE_URL, json=phone_body(service_id))
    response = owner.post(PHONE_URL, json=phone_body(service_id, customer_phone="9123456789"))
    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "slot_unavailable", "message": "This time is no longer free. Pick another time."}
    }


def test_bad_phone_gives_422_on_the_field(sign_up_owner):
    owner, business_id, service_id = make_shop(sign_up_owner)
    response = owner.post(PHONE_URL, json=phone_body(service_id, customer_phone="12345"))
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [
        {"field": "customer_phone", "message": "Enter a valid Indian mobile number."}
    ]
    assert customers(business_id) == []


def test_naive_time_is_refused(sign_up_owner):
    owner, business_id, service_id = make_shop(sign_up_owner)
    response = owner.post(PHONE_URL, json=phone_body(service_id, starts_at="2026-11-30T10:00:00"))
    assert response.status_code == 422
    assert bookings(business_id) == []


def test_staff_can_book(sign_up_owner, invite_member):
    # Behaviour: Staff have Inbox access, so they may book (FR-27). The Owner is the one Technician.
    owner, _, service_id = make_shop(sign_up_owner)
    staff = invite_member(owner, ["staff"])
    response = staff.client.post(PHONE_URL, json=phone_body(service_id))
    assert response.status_code == 201, response.text


def test_technician_only_gets_403(sign_up_owner):
    owner, business_id, service_id = make_shop(sign_up_owner)
    set_owner_roles(business_id, ["technician"])
    assert owner.post(PHONE_URL, json=phone_body(service_id)).status_code == 403
    assert owner.post(chat_url(new_chat(business_id)), json=phone_body(service_id)).status_code == 403
    assert all(customer.phone is None for customer in customers(business_id))  # only the chat's Customer
    assert bookings(business_id) == []


def test_booking_from_a_conversation(sign_up_owner):
    # Behaviour: a Booking made from a chat belongs to that chat's Customer, and the chat
    # state stays as it was.
    owner, business_id, service_id = make_shop(sign_up_owner)
    conversation_id = new_chat(business_id)
    response = owner.post(
        chat_url(conversation_id), json={"service_id": str(service_id), "starts_at": MON_10.isoformat()}
    )
    assert response.status_code == 201, response.text
    with Session(get_engine()) as session:
        conversation = session.get(Conversation, conversation_id)
    assert response.json()["conversation_id"] == str(conversation_id)
    assert response.json()["customer_id"] == str(conversation.customer_id)
    assert conversation.state == "agent"


def test_unknown_conversation_is_404(sign_up_owner):
    owner, _, service_id = make_shop(sign_up_owner)
    response = owner.post(chat_url(uuid.uuid4()), json={"service_id": str(service_id), "starts_at": MON_10.isoformat()})
    assert response.status_code == 404


def test_same_new_phone_at_once_makes_one_customer(sign_up_owner):
    # Behaviour: two phone-ins with one NEW phone at the same moment both work, and make ONE
    # Customer. The capacity lock is taken BEFORE the phone lookup, so the second call waits,
    # then finds the first call's Customer. (Lookup first: both find nobody, and the second
    # INSERT breaks the unique phone rule: a 500.)
    _, business_id, service_id = make_shop(sign_up_owner)
    actor = owner_actor(business_id)
    first_data = PhoneBookingIn(**phone_body(service_id))
    second_data = PhoneBookingIn(**phone_body(service_id, MON_10 + HOUR))
    result: dict = {}

    def second() -> None:
        try:
            with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
                result["booking"] = inbox_service.create_phone_booking(session, actor, second_data)
        except BaseException as error:  # noqa: BLE001 - checked by the asserts
            result["error"] = error

    with Session(get_engine()) as first, tenant_scope(business_id):
        first.begin()
        inbox_service.create_phone_booking(first, actor, first_data)  # not committed yet
        thread = threading.Thread(target=second)
        thread.start()
        thread.join(timeout=1)
        first.commit()
    thread.join(timeout=10)

    assert "booking" in result, result
    assert len(customers(business_id)) == 1
    assert len(bookings(business_id)) == 2

# Delete a Customer and all their data (story 4.5, NFR-8, AR-11, AD-13).
# Part 1 calls the service directly: each call runs in its own Session and transaction,
# like one request (AD-15). Part 2 (the routes) is further down.
import threading
import time
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from tests.integration.conftest import assert_not_found, set_owner_roles
from tests.integration.test_chat_messages import post
from tests.integration.test_chat_poll import poll
from tests.integration.test_inbox_list import new_chat
from tests.integration.test_inbox_reply import owner_actor

from app.core.db import get_engine
from app.core.errors import NotFound
from app.core.tenancy import tenant_scope
from app.core.tokens import new_token
from app.modules.inbox import service
from app.modules.inbox.models import Conversation, Customer, Message, VisitorToken
from app.modules.inbox.schemas import CustomerOut


def customer_of(conversation_id: uuid.UUID) -> uuid.UUID:
    with Session(get_engine()) as session:
        return session.get(Conversation, conversation_id).customer_id


def details(business_id: uuid.UUID, conversation_id: uuid.UUID) -> CustomerOut:
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        return service.customer_details(session, owner_actor(business_id), conversation_id)


def delete(business_id: uuid.UUID, customer_id: uuid.UUID) -> None:
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        service.delete_customer(session, owner_actor(business_id), customer_id)


def rows_left(customer_id: uuid.UUID, conversation_id: uuid.UUID, visitor_token_id: uuid.UUID) -> dict[str, int]:
    """How many rows of this Customer are still in each table (a direct read, no tenant rules)."""

    def count(model, where) -> int:
        return session.scalar(select(func.count()).select_from(model).where(where))

    with Session(get_engine()) as session:
        return {
            "customers": count(Customer, Customer.id == customer_id),
            "visitor_tokens": count(VisitorToken, VisitorToken.id == visitor_token_id),
            "conversations": count(Conversation, Conversation.id == conversation_id),
            "messages": count(Message, Message.conversation_id == conversation_id),
        }


def ids_of(conversation_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    with Session(get_engine()) as session:
        conversation = session.get(Conversation, conversation_id)
        return conversation.customer_id, conversation.visitor_token_id


NONE_LEFT = {"customers": 0, "visitor_tokens": 0, "conversations": 0, "messages": 0}


def test_details_counts_their_data(sign_up_owner):
    # Behaviour: the sheet's numbers are this Customer's: 1 Conversation, 2 Messages.
    _, business_id = sign_up_owner()
    token = new_token()
    conversation_id = new_chat(business_id, "one", token=token)
    new_chat(business_id, "two", token=token)  # same browser: the same Conversation
    new_chat(business_id, "someone else")  # another Customer: not counted
    answer = details(business_id, conversation_id)
    assert answer.customer_id == customer_of(conversation_id)
    assert (answer.conversation_count, answer.message_count) == (1, 2)


def test_delete_removes_all_their_rows(sign_up_owner):
    # Behaviour: after the delete, the Customer, their visitor token, Conversation, and
    # Messages are all gone from the database.
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    customer_id, token_id = ids_of(conversation_id)
    delete(business_id, customer_id)
    assert rows_left(customer_id, conversation_id, token_id) == NONE_LEFT


def test_delete_keeps_other_customers(sign_up_owner):
    # Behaviour: another Customer in the SAME Business keeps every row.
    _, business_id = sign_up_owner()
    gone = new_chat(business_id, "delete me")
    kept = new_chat(business_id, "keep me")
    delete(business_id, customer_of(gone))
    customer_id, token_id = ids_of(kept)
    assert rows_left(customer_id, kept, token_id) == {
        "customers": 1,
        "visitor_tokens": 1,
        "conversations": 1,
        "messages": 1,
    }


def test_delete_missing_or_twice_is_404(sign_up_owner):
    # Behaviour: an unknown id, or a Customer already deleted, is a 404 (NotFound).
    _, business_id = sign_up_owner()
    customer_id = customer_of(new_chat(business_id))
    delete(business_id, customer_id)
    with pytest.raises(NotFound):
        delete(business_id, customer_id)
    with pytest.raises(NotFound):
        delete(business_id, uuid.uuid7())


def test_deleted_cookie_opens_no_conversation(client, shop):
    # Behaviour: after the delete, the Customer's browser (same cookie) sees no chat, also on
    # the fast poll path with its old cursor. Its next send starts a NEW Customer.
    post(client, shop.slug, "my phone is 98xxxxxx")
    cursor = poll(client, shop.slug)["cursor"]
    assert poll(client, shop.slug, cursor)["changed"] is False  # the fast path is in use
    with Session(get_engine()) as session:
        old_customer = session.scalars(select(Customer.id).where(Customer.business_id == shop.business_id)).one()

    delete(shop.business_id, old_customer)

    after = poll(client, shop.slug, cursor)
    assert (after["changed"], after["messages"], after["snapshot"]) == (True, [], None)
    assert poll(client, shop.slug)["messages"] == []
    post(client, shop.slug, "hello again")
    with Session(get_engine()) as session:
        customers = session.scalars(select(Customer.id).where(Customer.business_id == shop.business_id)).all()
    assert len(customers) == 1 and customers[0] != old_customer


def test_delete_waits_for_a_send(sign_up_owner):
    # Behaviour: a delete WAITS while a Customer send holds the visitor token lock (the send's
    # first lock), then deletes that send's new Message too. No deadlock, nothing left behind.
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    customer_id, token_id = ids_of(conversation_id)
    result: dict[str, BaseException | None] = {}

    def run_delete() -> None:
        try:
            delete(business_id, customer_id)
            result["error"] = None
        except BaseException as error:  # noqa: BLE001 - reported by the assert below
            result["error"] = error

    with get_engine().connect() as conn:
        tx = conn.begin()
        # Play "a Customer send in progress": lock 1 (visitor token), lock 2 (Conversation),
        # then a new Message, not yet committed.
        conn.execute(text("SELECT id FROM visitor_tokens WHERE id = :id FOR UPDATE"), {"id": token_id})
        conn.execute(text("SELECT id FROM conversations WHERE id = :id FOR UPDATE"), {"id": conversation_id})
        conn.execute(
            text(
                "INSERT INTO messages (id, business_id, conversation_id, seq, author_type, body, lang)"
                " VALUES (:id, :b, :c, 2, 'customer', 'one more', 'en')"
            ),
            {"id": uuid.uuid7(), "b": business_id, "c": conversation_id},
        )
        thread = threading.Thread(target=run_delete)
        thread.start()
        time.sleep(0.5)
        assert thread.is_alive(), "the delete did not wait for the send's lock"
        tx.commit()
        thread.join(timeout=30)
    assert not thread.is_alive(), "the delete never finished"
    assert result["error"] is None, result["error"]
    assert rows_left(customer_id, conversation_id, token_id) == NONE_LEFT


# ---------------------------------------------------------------- Part 2: the routes


def customer_url(conversation_id) -> str:
    return f"/api/v1/inbox/conversations/{conversation_id}/customer"


def delete_url(customer_id) -> str:
    return f"/api/v1/inbox/customers/{customer_id}"


def test_owner_deletes_by_route(sign_up_owner):
    # Behaviour: the Owner reads the sheet, deletes with 204, and then the chat is a 404.
    owner, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    sheet = owner.get(customer_url(conversation_id))
    assert sheet.status_code == 200, sheet.text
    assert sheet.json()["message_count"] == 1
    response = owner.delete(delete_url(sheet.json()["customer_id"]))
    assert response.status_code == 204, response.text
    assert_not_found(owner.get(f"/api/v1/inbox/conversations/{conversation_id}/messages"))


@pytest.mark.parametrize("roles", [["staff"], ["technician"], ["staff", "technician"]])
def test_only_the_owner_may_delete(sign_up_owner, roles):
    # Behaviour: Staff and Technicians get 403 on both routes (FR-10), and nothing is deleted.
    # The Role check runs first, so a made-up id gets the same 403 (no hint that ids exist).
    owner, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    customer_id, token_id = ids_of(conversation_id)
    set_owner_roles(business_id, roles)
    statuses = [
        owner.get(customer_url(conversation_id)).status_code,
        owner.delete(delete_url(customer_id)).status_code,
        owner.get(customer_url(uuid.uuid4())).status_code,
        owner.delete(delete_url(uuid.uuid4())).status_code,
    ]
    assert statuses == [403, 403, 403, 403]
    assert rows_left(customer_id, conversation_id, token_id)["messages"] == 1

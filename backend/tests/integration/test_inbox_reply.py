# Team replies and the Handoff state (story 4.4, FR-21, FR-24, AD-10).
# Part 1 calls the service directly, below the HTTP layer: each call runs in its own Session
# and transaction, like one request (AD-15). Part 2 (the routes) is further down.
import threading
import time
import uuid

import pytest
import redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tests.integration.conftest import _owner_membership, assert_not_found, set_owner_roles
from tests.integration.test_chat_messages import post
from tests.integration.test_chat_poll import conversation_of, poll
from tests.integration.test_inbox_list import new_chat, set_state
from tests.integration.test_tenant_isolation import _setup

from app.core.db import get_engine
from app.core.errors import AppError
from app.core.tenancy import tenant_scope
from app.core.tokens import new_token
from app.core.versions import read_version
from app.modules.accounts.schemas import Actor
from app.modules.inbox import service
from app.modules.inbox.models import Conversation, Message
from app.modules.inbox.repository import ConversationRepository
from app.modules.inbox.schemas import ChatCursor, MessageOut, SendMessageIn


def owner_actor(business_id: uuid.UUID) -> Actor:
    """The Owner of this Business as an Actor, the way a logged-in request would see them."""
    membership = _owner_membership(business_id)
    return Actor(
        user_id=membership.user_id,
        membership_id=membership.id,
        business_id=business_id,
        roles=set(membership.roles),
    )


def reply(business_id: uuid.UUID, conversation_id: uuid.UUID, body: str = "On my way", client_id=None) -> MessageOut:
    data = SendMessageIn(body=body, client_message_id=client_id or uuid.uuid4())
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        return service.reply(session, owner_actor(business_id), conversation_id, data)


def take_over(business_id: uuid.UUID, conversation_id: uuid.UUID) -> str:
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        return service.take_over(session, owner_actor(business_id), conversation_id).state


def give_back(business_id: uuid.UUID, conversation_id: uuid.UUID) -> str:
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        return service.give_back(session, owner_actor(business_id), conversation_id).state


def row(conversation_id: uuid.UUID) -> Conversation:
    # A direct database read, outside the app's tenant rules, so the test sees the truth.
    with Session(get_engine()) as session:
        return session.get(Conversation, conversation_id)


def messages(conversation_id: uuid.UUID) -> list[Message]:
    with Session(get_engine()) as session:
        query = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.seq)
        return list(session.scalars(query))


def test_reply_saves_a_user_message(sign_up_owner):
    # Behaviour: a team reply is saved as the NEXT Message, written by that team member.
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    customer_time = row(conversation_id).last_message_at
    saved = reply(business_id, conversation_id)
    assert (saved.seq, saved.author_type, saved.body) == (2, "user", "On my way")
    assert messages(conversation_id)[-1].author_membership_id == owner_actor(business_id).membership_id
    after = row(conversation_id)
    assert after.last_seq == 2
    assert after.last_message_at >= customer_time


def test_reply_starts_handoff(sign_up_owner):
    # Behaviour: replying pauses the Agent: the state becomes handoff (FR-24).
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    reply(business_id, conversation_id)
    assert row(conversation_id).state == "handoff"


def test_reply_retry_saves_once(sign_up_owner):
    # Behaviour: a retry with the same client_message_id hands back the saved Message, no copy.
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    client_id = uuid.uuid4()
    first = reply(business_id, conversation_id, client_id=client_id)
    second = reply(business_id, conversation_id, client_id=client_id)
    assert first.seq == second.seq == 2
    assert len(messages(conversation_id)) == 2


def test_take_over_and_give_back(sign_up_owner):
    # Behaviour: "Take over" sets handoff; "Give back to Agent" sets agent (FR-21).
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    assert take_over(business_id, conversation_id) == "handoff"
    assert give_back(business_id, conversation_id) == "agent"
    assert row(conversation_id).state == "agent"


def test_end_handoff_only_from_handoff(sign_up_owner):
    # Behaviour: Give back on a chat the Agent already has changes nothing, so open screens
    # are not told "something changed" (no version bump).
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    before = read_version(business_id, conversation_id)
    assert give_back(business_id, conversation_id) == "agent"
    assert read_version(business_id, conversation_id) == before


def test_start_handoff_twice_bumps_once(sign_up_owner):
    # Behaviour: a second Take over is a no-op: the version goes up once, not twice.
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    before = read_version(business_id, conversation_id) or 0
    take_over(business_id, conversation_id)
    once = read_version(business_id, conversation_id)
    take_over(business_id, conversation_id)
    assert once is not None and once > before
    assert read_version(business_id, conversation_id) == once


def test_take_over_reopens_a_closed_chat(sign_up_owner):
    # Behaviour: a team member can pick up a closed chat again; it goes to handoff.
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    set_state(conversation_id, "closed")
    assert take_over(business_id, conversation_id) == "handoff"


def test_reply_waits_for_the_conversation_lock(sign_up_owner):
    # Behaviour: a reply WAITS while someone else holds the Conversation row lock, then reads the
    # NEW last_seq. (Without the lock it would not wait; without a fresh read it would reuse a seq.)
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    result: dict[str, MessageOut | BaseException] = {}

    def team_reply() -> None:
        try:
            result["saved"] = reply(business_id, conversation_id, "waits")
        except BaseException as error:  # noqa: BLE001 - reported by the assert below
            result["saved"] = error

    with get_engine().connect() as conn:
        tx = conn.begin()
        # Play "a Customer send in progress": hold the lock on this Conversation row.
        conn.execute(text("SELECT id FROM conversations WHERE id = :id FOR UPDATE"), {"id": conversation_id})
        thread = threading.Thread(target=team_reply)
        thread.start()
        time.sleep(0.5)
        assert thread.is_alive(), "the reply did not wait for the Conversation lock"
        conn.execute(text("UPDATE conversations SET last_seq = 5 WHERE id = :id"), {"id": conversation_id})
        tx.commit()
        thread.join(timeout=30)
    assert not thread.is_alive(), "the reply never finished"
    assert isinstance(result["saved"], MessageOut), result["saved"]
    assert result["saved"].seq == 6


def test_poll_reads_state_after_version(sign_up_owner, monkeypatch):
    # Behaviour: a poll never pairs an OLD state with a NEW version. Here a take-over commits
    # between the poll loading the row and reading the version; the answer must say handoff.
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    real = service.read_or_seed_version

    def take_over_first(bid, cid):
        set_state(cid, "handoff")  # another request commits right now
        return real(bid, cid)

    monkeypatch.setattr(service, "read_or_seed_version", take_over_first)
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        conversation = ConversationRepository(session).get(conversation_id)  # loaded: state agent
        answer = service.poll_conversation(session, conversation, 0)
    assert answer.snapshot.conversation_state == "handoff"


# ---------------------------------------------------------------- Part 2: the routes (HTTP)


def thread_url(conversation_id) -> str:
    return f"/api/v1/inbox/conversations/{conversation_id}/messages"


def take_over_url(conversation_id) -> str:
    return f"/api/v1/inbox/conversations/{conversation_id}/take-over"


def give_back_url(conversation_id) -> str:
    return f"/api/v1/inbox/conversations/{conversation_id}/give-back"


def reply_body(text: str = "On my way") -> dict:
    return {"body": text, "client_message_id": str(uuid.uuid4())}


def all_routes(client, conversation_id) -> list:
    """One call to each of the 4 team routes, for checks that apply to all of them."""
    return [
        client.get(thread_url(conversation_id)),
        client.post(thread_url(conversation_id), json=reply_body()),
        client.post(take_over_url(conversation_id)),
        client.post(give_back_url(conversation_id)),
    ]


def open_thread(client, conversation_id, cursor: str | None = None) -> dict:
    params = {} if cursor is None else {"cursor": cursor}
    response = client.get(thread_url(conversation_id), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_open_conversation_shows_full_history(sign_up_owner):
    # Behaviour: opening a chat shows every Message, oldest first, and who replies now.
    owner, business_id = sign_up_owner()
    token = new_token()
    conversation_id = new_chat(business_id, "first", token)
    new_chat(business_id, "second", token)
    answer = open_thread(owner, conversation_id)
    assert answer["changed"] is True
    assert [m["body"] for m in answer["messages"]] == ["first", "second"]
    assert answer["snapshot"] == {"conversation_state": "agent"}
    assert answer["cursor"]


def test_thread_poll_no_change(sign_up_owner):
    # Behaviour: a poll with the newest cursor says "no change" and sends no Messages.
    owner, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    cursor = open_thread(owner, conversation_id)["cursor"]
    again = open_thread(owner, conversation_id, cursor)
    assert (again["changed"], again["messages"]) == (False, [])


def test_reply_route(sign_up_owner):
    # Behaviour: a reply is saved, and the next poll shows it and the handoff state.
    owner, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    cursor = open_thread(owner, conversation_id)["cursor"]
    response = owner.post(thread_url(conversation_id), json=reply_body())
    assert response.status_code == 201, response.text
    assert response.json()["author_type"] == "user"
    after = open_thread(owner, conversation_id, cursor)
    assert after["changed"] is True
    assert [m["body"] for m in after["messages"]] == ["On my way"]
    assert after["snapshot"] == {"conversation_state": "handoff"}


def test_chat_page_poll_sees_team_reply(sign_up_owner, make_client):
    # Behaviour: the Customer's open Chat Page gets the team reply on its next poll (FR-24).
    owner, business_id = sign_up_owner()
    slug = _setup(owner)["chat_slug"]
    customer = make_client()
    assert poll(customer, slug)["cursor"] is None  # first visit: sets the cookie
    assert post(customer, slug).status_code == 201
    cursor = poll(customer, slug)["cursor"]
    assert poll(customer, slug, cursor)["changed"] is False  # the fast path is warm
    conversation_id = conversation_of(business_id).id
    assert owner.post(thread_url(conversation_id), json=reply_body()).status_code == 201
    answer = poll(customer, slug, cursor)
    assert answer["changed"] is True
    assert [(m["author_type"], m["body"]) for m in answer["messages"]] == [("user", "On my way")]


def test_take_over_and_give_back_routes(sign_up_owner):
    owner, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    taken = owner.post(take_over_url(conversation_id))
    assert (taken.status_code, taken.json()) == (200, {"state": "handoff"})
    given = owner.post(give_back_url(conversation_id))
    assert (given.status_code, given.json()) == (200, {"state": "agent"})


def test_state_change_adds_a_span_event(sign_up_owner, spans):
    # Behaviour: a state change leaves a note in the request's trace: the two states, nothing more.
    owner, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    spans.clear()
    assert owner.post(take_over_url(conversation_id)).status_code == 200
    events = [e for s in spans.finished() for e in s.events if e.name == "conversation.state_changed"]
    assert [dict(e.attributes) for e in events] == [{"from": "agent", "to": "handoff"}]


def test_other_business_conversation_is_404(sign_up_owner):
    # Behaviour: an id from another Business looks like a missing one, and nothing changes there.
    owner_a, _ = sign_up_owner()
    _, business_b = sign_up_owner()
    conversation_b = new_chat(business_b)
    for response in all_routes(owner_a, conversation_b):
        assert_not_found(response)
    assert len(messages(conversation_b)) == 1
    assert row(conversation_b).state == "agent"


def test_fast_path_other_business_is_404(sign_up_owner):
    # Behaviour: a cursor never opens another Business's chat, even one that names it exactly.
    owner_a, business_a = sign_up_owner()
    owner_b, business_b = sign_up_owner()
    conversation_b = new_chat(business_b)
    open_thread(owner_b, conversation_b)  # B's own poll seeds B's version
    version_b = read_version(business_b, conversation_b)
    for business_id in (business_b, business_a):
        cursor = ChatCursor(business_id=business_id, after_seq=1, version=version_b).format()
        assert_not_found(owner_a.get(thread_url(conversation_b), params={"cursor": cursor}))


def test_technician_gets_403_on_team_routes(sign_up_owner):
    # Behaviour: a Technician-only member may not read or change chats (FR-10).
    owner, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    set_owner_roles(business_id, ["technician"])
    assert [r.status_code for r in all_routes(owner, conversation_id)] == [403, 403, 403, 403]
    assert row(conversation_id).state == "agent"


def test_technician_gets_403_even_for_a_missing_id(sign_up_owner):
    # Behaviour: the Role check runs BEFORE the lookup, so a Technician cannot tell
    # real ids from made-up ones (both give the same answer).
    owner, business_id = sign_up_owner()
    set_owner_roles(business_id, ["technician"])
    missing_id = uuid.uuid4()
    responses = all_routes(owner, missing_id)
    assert [r.status_code for r in responses] == [403, 403, 403, 403]


def test_reply_bad_body_is_422(sign_up_owner):
    owner, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)
    response = owner.post(thread_url(conversation_id), json=reply_body("   "))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["fields"] == [{"field": "body", "message": "Write a message first."}]


def test_bad_conversation_id_is_422(sign_up_owner):
    owner, _ = sign_up_owner()
    assert owner.get(thread_url("abc")).status_code == 422


def test_poll_for_member_redis_down_is_503(sign_up_owner, monkeypatch):
    # Behaviour: without Redis the poll cannot tell "no change", so it refuses (fail closed).
    _, business_id = sign_up_owner()
    conversation_id = new_chat(business_id)

    def redis_down(*_):
        raise redis.RedisError("down")

    monkeypatch.setattr(service, "read_version", redis_down)
    cursor = ChatCursor(business_id=business_id, after_seq=1, version=1).format()
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        with pytest.raises(AppError) as raised:
            service.poll_for_member(session, owner_actor(business_id), conversation_id, cursor)
    assert raised.value.status_code == 503

# Team replies and the Handoff state (story 4.4, FR-21, FR-24, AD-10).
# Part 1 calls the service directly, below the HTTP layer: each call runs in its own Session
# and transaction, like one request (AD-15). Part 2 (the routes) is further down.
import threading
import time
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tests.integration.conftest import _owner_membership
from tests.integration.test_inbox_list import new_chat, set_state

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.core.versions import read_version
from app.modules.accounts.schemas import Actor
from app.modules.inbox import service
from app.modules.inbox.models import Conversation, Message
from app.modules.inbox.repository import ConversationRepository
from app.modules.inbox.schemas import MessageOut, SendMessageIn


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

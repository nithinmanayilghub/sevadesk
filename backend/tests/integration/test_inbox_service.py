# The inbox save logic (story 4.1, AR-12, AD-16), called directly, below the HTTP layer.
# Each send runs in its own Session and transaction, like one request (AD-15).
import hashlib
import threading
import time
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.core.tenancy import current_business_id, tenant_scope
from app.core.tokens import new_token
from app.modules.inbox import service
from app.modules.inbox.models import Conversation, Customer, Message, VisitorToken
from app.modules.inbox.repository import ConversationRepository
from app.modules.inbox.schemas import MessageOut, SendMessageIn
from app.modules.inbox.webchat import WebchatChannel


def send(business_id: uuid.UUID, token: str, body: str = "Fan not working", client_id: uuid.UUID | None = None):
    """One send, as one request would do it: its own transaction, inside the Business."""
    data = SendMessageIn(body=body, client_message_id=client_id or uuid.uuid4())
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        return service.receive_message(session, WebchatChannel(token), data)


def bodies(business_id: uuid.UUID, token: str) -> list[str]:
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        conversation = WebchatChannel(token).find_conversation(session)
        return [m.body for m in service.poll_conversation(session, conversation, 0).messages]


def count(model, business_id: uuid.UUID) -> int:
    # A direct database read, outside the app's tenant rules, so the test sees the truth.
    with Session(get_engine()) as session:
        return session.scalar(select(func.count()).select_from(model).where(model.business_id == business_id))


def test_first_send_starts_customer_and_conversation(sign_up_owner):
    _, business_id = sign_up_owner()
    saved = send(business_id, new_token())
    assert (saved.seq, saved.author_type, saved.actions, saved.lang) == (1, "customer", [], "en")
    assert (count(Customer, business_id), count(Conversation, business_id)) == (1, 1)
    with Session(get_engine()) as session:
        conversation = session.scalars(select(Conversation).where(Conversation.business_id == business_id)).one()
        assert (conversation.state, conversation.last_seq) == ("agent", 1)


def test_seq_goes_up_by_one(sign_up_owner):
    _, business_id = sign_up_owner()
    token = new_token()
    assert [send(business_id, token, f"m{n}").seq for n in range(3)] == [1, 2, 3]
    assert count(Conversation, business_id) == 1


def test_same_client_message_id_saves_once(sign_up_owner):
    _, business_id = sign_up_owner()
    token, client_id = new_token(), uuid.uuid4()
    first = send(business_id, token, client_id=client_id)
    again = send(business_id, token, client_id=client_id)
    assert again == first
    assert count(Message, business_id) == 1


def test_retry_of_saved_message_skips_the_limit(sign_up_owner, monkeypatch):
    # A retry of a Message that was already saved is not a new Message, so it never gets 429.
    monkeypatch.setattr(service, "CHAT_SEND_CONVERSATION_LIMIT", 1)
    _, business_id = sign_up_owner()
    token, client_id = new_token(), uuid.uuid4()
    first = send(business_id, token, client_id=client_id)
    assert send(business_id, token, client_id=client_id) == first


def test_conversation_limit_returns_429(sign_up_owner, monkeypatch):
    monkeypatch.setattr(service, "CHAT_SEND_CONVERSATION_LIMIT", 2)
    _, business_id = sign_up_owner()
    token = new_token()
    send(business_id, token)
    send(business_id, token)
    with pytest.raises(service.TooManyMessages) as caught:
        send(business_id, token)
    assert caught.value.status_code == 429
    assert int(caught.value.headers["Retry-After"]) > 0
    assert count(Message, business_id) == 2


def test_token_stored_only_as_hash(sign_up_owner):
    _, business_id = sign_up_owner()
    token = new_token()
    send(business_id, token)
    with Session(get_engine()) as session:
        row = session.scalars(select(VisitorToken).where(VisitorToken.business_id == business_id)).one()
        assert row.token_hash == hashlib.sha256(f"{business_id}:{token}".encode()).hexdigest()
        # The raw token is in no column of any inbox table.
        for table in ("customers", "visitor_tokens", "conversations", "messages"):
            found = session.execute(
                text(f"SELECT count(*) FROM {table} t WHERE t::text LIKE :token"), {"token": f"%{token}%"}
            )
            assert found.scalar() == 0, table


def test_same_cookie_gets_a_different_hash_per_business(sign_up_owner):
    # One browser cookie reaches every slug. Each Business stores a different hash, so the
    # database cannot link the same visitor across Businesses.
    _, a = sign_up_owner()
    _, b = sign_up_owner()
    token = new_token()
    send(a, token)
    send(b, token)
    with Session(get_engine()) as session:
        hashes = session.scalars(select(VisitorToken.token_hash).where(VisitorToken.business_id.in_([a, b]))).all()
    assert len(set(hashes)) == 2


def test_list_messages_is_own_conversation_only(sign_up_owner):
    _, business_id = sign_up_owner()
    x, y = new_token(), new_token()
    send(business_id, x, "from x")
    send(business_id, y, "from y")
    assert bodies(business_id, x) == ["from x"]
    assert bodies(business_id, y) == ["from y"]


def test_list_with_unknown_token_writes_nothing(sign_up_owner):
    _, business_id = sign_up_owner()
    assert bodies(business_id, new_token()) == []
    assert count(VisitorToken, business_id) == 0


def test_send_waits_for_the_conversation_lock(sign_up_owner):
    # Behaviour: a send WAITS while someone else holds the Conversation row lock (AR-12). When it
    # may go on, it reads the NEW last_seq, not an old copy. (Without the lock it would not
    # wait; without a fresh read it would reuse seq 2 and crash on the UNIQUE rule.)
    _, business_id = sign_up_owner()
    token = new_token()
    send(business_id, token)  # seq 1: the Conversation exists now
    with Session(get_engine()) as session:
        conversation_id = session.scalars(select(Conversation.id).where(Conversation.business_id == business_id)).one()

    result: dict[str, MessageOut | BaseException] = {}

    def second_send() -> None:
        # A new thread does not get our ContextVars, so send() enters tenant_scope itself.
        try:
            result["saved"] = send(business_id, token, "waits")
        except BaseException as error:  # noqa: BLE001 - reported by the assert below
            result["saved"] = error

    with get_engine().connect() as conn:
        tx = conn.begin()
        # Play "a staff reply in progress": hold the lock on this Conversation row.
        conn.execute(text("SELECT id FROM conversations WHERE id = :id FOR UPDATE"), {"id": conversation_id})
        thread = threading.Thread(target=second_send)
        thread.start()
        time.sleep(0.5)
        assert thread.is_alive(), "the send did not wait for the Conversation lock"
        # The staff reply finishes: it used seqs up to 5.
        conn.execute(text("UPDATE conversations SET last_seq = 5 WHERE id = :id"), {"id": conversation_id})
        tx.commit()
        thread.join(timeout=30)
    assert not thread.is_alive(), "the send never finished"
    assert isinstance(result["saved"], MessageOut), result["saved"]
    assert result["saved"].seq == 6


def test_locked_read_refreshes_a_row_already_loaded(sign_up_owner):
    # Behaviour: code that reads a Conversation first and locks it later (a staff reply, Story
    # 4.4) must see the NEWEST last_seq after the lock, not the copy SQLAlchemy kept in memory.
    _, business_id = sign_up_owner()
    send(business_id, new_token())
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        repository = ConversationRepository(session)
        loaded = session.scalars(select(Conversation).where(Conversation.business_id == business_id)).one()
        assert loaded.last_seq == 1
        # Meanwhile another request raises last_seq and commits.
        with get_engine().begin() as other:
            other.execute(text("UPDATE conversations SET last_seq = 7 WHERE id = :id"), {"id": loaded.id})
        locked = repository.newest_for_visitor(loaded.visitor_token_id, lock=True)
        assert locked is loaded  # the same in-memory object …
        assert locked.last_seq == 7  # … but refreshed with the value the lock now protects


def test_first_sends_from_one_browser_share_one_conversation(sign_up_owner):
    # Behaviour: two first sends at the same moment (a double tap) make ONE Conversation.
    _, business_id = sign_up_owner()
    token = new_token()
    start = threading.Barrier(2)
    seqs: list[int] = []

    def first_send() -> None:
        start.wait()
        seqs.append(send(business_id, token).seq)

    threads = [threading.Thread(target=first_send) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(seqs) == [1, 2]
    assert count(Conversation, business_id) == 1


def test_hindi_body_gets_lang_hi(sign_up_owner):
    _, business_id = sign_up_owner()
    token = new_token()
    assert send(business_id, token, "नमस्ते").lang == "hi"
    assert send(business_id, token, "namaste").lang == "en"


class FakeChannel:
    """A second channel, made only for this test: it always uses one Conversation it made."""

    def __init__(self):
        self.conversation_id: uuid.UUID | None = None

    def find_conversation(self, session: Session) -> Conversation | None:
        return session.get(Conversation, self.conversation_id) if self.conversation_id else None

    def open_conversation(self, session: Session) -> Conversation:
        if self.conversation_id is None:
            business_id = current_business_id()
            customer = Customer(business_id=business_id)
            visitor = VisitorToken(business_id=business_id, token_hash=uuid.uuid4().hex)
            session.add_all([customer, visitor])
            session.flush()
            conversation = Conversation(business_id=business_id, customer_id=customer.id, visitor_token_id=visitor.id)
            session.add(conversation)
            session.flush()
            self.conversation_id = conversation.id
        return session.get(Conversation, self.conversation_id, with_for_update=True, populate_existing=True)


def test_another_channel_needs_no_service_change(sign_up_owner):
    # NFR-9: a new channel (say WhatsApp) is a new adapter. receive_message stays as it is.
    _, business_id = sign_up_owner()
    channel = FakeChannel()
    for body in ("one", "two"):
        with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
            service.receive_message(session, channel, SendMessageIn(body=body, client_message_id=uuid.uuid4()))
    with Session(get_engine()) as session, tenant_scope(business_id):
        answer = service.poll_conversation(session, channel.find_conversation(session), 0)
        assert [m.body for m in answer.messages] == ["one", "two"]


def _last_message_at(business_id: uuid.UUID):
    # A direct database read of the one Conversation in this Business.
    with Session(get_engine()) as session:
        return session.scalars(
            select(Conversation.last_message_at).where(Conversation.business_id == business_id)
        ).one()


def test_last_message_at_follows_the_newest_message(sign_up_owner):
    # Behaviour: the Conversation remembers when its newest Message arrived (the Inbox order, story 4.3).
    _, business_id = sign_up_owner()
    token = new_token()
    send(business_id, token, "first")
    second = send(business_id, token, "second")
    assert _last_message_at(business_id) == second.created_at


def test_retry_leaves_last_message_at_unchanged(sign_up_owner):
    # Behaviour: a retry of a saved Message is not new activity, so the time stays.
    _, business_id = sign_up_owner()
    token, client_id = new_token(), uuid.uuid4()
    send(business_id, token, "hello", client_id)
    before = _last_message_at(business_id)
    send(business_id, token, "hello", client_id)
    assert _last_message_at(business_id) == before


def test_last_message_at_never_moves_back(sign_up_owner):
    # Behaviour: a send whose transaction started earlier cannot move the time back.
    _, business_id = sign_up_owner()
    token = new_token()
    send(business_id, token, "first")
    with get_engine().begin() as connection:
        connection.execute(
            text("UPDATE conversations SET last_message_at = '2099-01-01 00:00+00' WHERE business_id = :b"),
            {"b": business_id},
        )
    send(business_id, token, "second")
    assert _last_message_at(business_id).year == 2099

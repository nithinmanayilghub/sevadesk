# The Chat Page poll (story 4.2, AD-7): GET /chat/{slug}/messages?cursor=…
# It answers with only the Messages after the cursor, a snapshot, and a new cursor.
# Each TestClient is one browser: it keeps its cookies, like a real one.
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from tests.integration.test_chat_messages import messages_url, post

from app.core.db import get_engine
from app.core.redis_client import get_redis
from app.core.versions import version_key
from app.modules.inbox.models import Conversation, Message, VisitorToken
from app.modules.inbox.repository import MessageRepository
from app.modules.inbox.schemas import ChatCursor


def poll(client, slug: str, cursor: str | None = None) -> dict:
    params = {} if cursor is None else {"cursor": cursor}
    response = client.get(messages_url(slug), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def seqs(answer: dict) -> list[int]:
    return [m["seq"] for m in answer["messages"]]


def conversation_of(business_id: uuid.UUID) -> Conversation:
    with Session(get_engine()) as session:
        return session.scalars(select(Conversation).where(Conversation.business_id == business_id)).one()


def test_first_poll_returns_all_and_a_cursor(client, shop):
    post(client, shop.slug, "one")
    post(client, shop.slug, "two")
    answer = poll(client, shop.slug)
    assert answer["changed"] is True
    assert seqs(answer) == [1, 2]
    assert answer["snapshot"] == {"conversation_state": "agent"}
    assert answer["cursor"] is not None


def test_poll_with_cursor_returns_only_new(client, shop):
    post(client, shop.slug)
    post(client, shop.slug)
    cursor = poll(client, shop.slug)["cursor"]
    post(client, shop.slug)
    assert seqs(poll(client, shop.slug, cursor)) == [3]


def test_no_conversation_has_no_cursor(client, shop):
    assert poll(client, shop.slug) == {"changed": True, "messages": [], "snapshot": None, "cursor": None}


def test_version_is_read_before_messages(client, shop, monkeypatch):
    post(client, shop.slug)
    key = version_key(shop.business_id, conversation_of(shop.business_id).id)
    real_list_after = MessageRepository.list_after

    def send_commits_in_between(self, conversation_id, after_seq):
        get_redis().incr(key)  # as if another send committed and bumped right now
        return real_list_after(self, conversation_id, after_seq)

    monkeypatch.setattr(MessageRepository, "list_after", send_commits_in_between)
    cursor = ChatCursor.parse(poll(client, shop.slug)["cursor"])
    # The cursor holds the number from BEFORE the Messages were read, so the next poll reads again.
    assert cursor.version != int(get_redis().get(key))


def test_cursor_after_seq_is_the_last_listed_seq(client, shop, monkeypatch):
    post(client, shop.slug)
    conversation_id = conversation_of(shop.business_id).id
    real_list_after = MessageRepository.list_after

    def agent_reply_commits_in_between(self, conv_id, after_seq):
        # Another transaction saves seq 2 AFTER the poll read the Conversation (last_seq was 1).
        with Session(get_engine()) as other, other.begin():
            other.execute(update(Conversation).where(Conversation.id == conversation_id).values(last_seq=2))
            other.add(
                Message(
                    business_id=shop.business_id,
                    conversation_id=conversation_id,
                    seq=2,
                    author_type="agent",
                    body="Hello",
                    lang="en",
                )
            )
        return real_list_after(self, conv_id, after_seq)

    monkeypatch.setattr(MessageRepository, "list_after", agent_reply_commits_in_between)
    answer = poll(client, shop.slug)
    assert seqs(answer) == [1, 2]
    assert ChatCursor.parse(answer["cursor"]).after_seq == 2  # not the older last_seq (1): no repeat


def test_forged_high_after_seq_still_sees_new_messages(client, shop):
    post(client, shop.slug)
    forged = ChatCursor(business_id=shop.business_id, after_seq=999_999_999, version=0).format()
    answer = poll(client, shop.slug, forged)
    assert seqs(answer) == []
    post(client, shop.slug, "after the forged cursor")
    assert [m["body"] for m in poll(client, shop.slug, answer["cursor"])["messages"]] == ["after the forged cursor"]


def _row_counts(business_id: uuid.UUID) -> tuple[int, ...]:
    with Session(get_engine()) as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model).where(model.business_id == business_id))
            for model in (VisitorToken, Conversation, Message)
        )


def test_poll_writes_no_database_rows(client, make_client, shop):
    post(client, shop.slug)
    before = _row_counts(shop.business_id)
    poll(client, shop.slug)
    poll(make_client(), shop.slug)  # a new browser too: a GET makes no visitor row (AD-5)
    assert _row_counts(shop.business_id) == before

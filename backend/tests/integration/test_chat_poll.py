# The Chat Page poll (story 4.2, AD-7): GET /chat/{slug}/messages?cursor=…
# It answers with only the Messages after the cursor, a snapshot, and a new cursor.
# Each TestClient is one browser: it keeps its cookies, like a real one.
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session
from tests.integration.conftest import assert_not_found
from tests.integration.test_chat_messages import messages_url, post
from tests.integration.test_tenant_isolation import _setup

from app.core.db import get_engine
from app.core.redis_client import get_redis
from app.core.settings import get_settings
from app.core.versions import version_key
from app.modules.inbox import chat_poll
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


# --- The fast "no change" path and the poll limit (story 4.2, Task 3) ---


@contextmanager
def postgres_use() -> Iterator[dict[str, int]]:
    """Count Postgres use inside the block: connections taken from the pool, and SQL statements."""
    used = {"checkouts": 0, "statements": 0}

    def on_checkout(*_):
        used["checkouts"] += 1

    def on_statement(*_):
        used["statements"] += 1

    engine = get_engine()
    event.listen(engine, "checkout", on_checkout)
    event.listen(engine, "before_cursor_execute", on_statement)
    try:
        yield used
    finally:
        event.remove(engine, "checkout", on_checkout)
        event.remove(engine, "before_cursor_execute", on_statement)


def test_no_change_poll_skips_postgres(client, shop):
    post(client, shop.slug)
    cursor = poll(client, shop.slug)["cursor"]
    with postgres_use() as used:
        answer = poll(client, shop.slug, cursor)
    assert answer == {"changed": False, "messages": [], "snapshot": None, "cursor": cursor}
    assert used == {"checkouts": 0, "statements": 0}


def test_change_after_send_takes_slow_path(client, shop):
    post(client, shop.slug)
    cursor = poll(client, shop.slug)["cursor"]
    post(client, shop.slug, "new one")
    answer = poll(client, shop.slug, cursor)
    assert answer["changed"] is True
    assert [m["body"] for m in answer["messages"]] == ["new one"]


def test_missing_version_key_is_slow_once_then_fast(client, shop):
    post(client, shop.slug)
    cursor = poll(client, shop.slug)["cursor"]
    get_redis().delete(version_key(shop.business_id, conversation_of(shop.business_id).id))
    answer = poll(client, shop.slug, cursor)
    assert answer["changed"] is True  # no version in Redis: never "no change"
    with postgres_use() as used:
        assert poll(client, shop.slug, answer["cursor"])["changed"] is False
    assert used["checkouts"] == 0


def test_forged_business_id_counts_nothing(client, shop):
    post(client, shop.slug)
    poll(client, shop.slug)  # writes the map for the real Business
    forged_id = uuid.uuid4()
    forged = ChatCursor(business_id=forged_id, after_seq=0, version=1).format()
    assert seqs(poll(client, shop.slug, forged)) == [1]  # the slow path, for the slug's own Business
    assert list(get_redis().scan_iter(f"chat_poll:ip:{forged_id}:*")) == []
    assert list(get_redis().scan_iter(f"chat_poll:ip:{shop.business_id}:*")) != []


def test_cursor_from_other_business_is_ignored(client, shop, sign_up_owner):
    owner_b, _ = sign_up_owner()
    b_slug = _setup(owner_b)["chat_slug"]
    post(client, b_slug)
    post(client, b_slug)
    post(client, shop.slug, "for A")
    b_cursor = poll(client, b_slug)["cursor"]  # after_seq 2, in Business B
    answer = poll(client, shop.slug, b_cursor)
    assert answer["changed"] is True
    assert [m["body"] for m in answer["messages"]] == ["for A"]  # from seq 1, not after B's seq 2


def test_cursor_with_another_cookie_is_slow(client, make_client, shop):
    post(client, shop.slug)
    cursor = poll(client, shop.slug)["cursor"]
    other = make_client()
    poll(other, shop.slug)  # browser 2 gets its own cookie, and has no chat
    assert poll(other, shop.slug, cursor)["messages"] == []


def test_bad_cursor_is_a_full_poll(client, shop):
    post(client, shop.slug)
    post(client, shop.slug)
    assert seqs(poll(client, shop.slug, "garbage")) == [1, 2]
    response = client.get(messages_url(shop.slug), params={"cursor": "v" * 200})
    assert response.status_code == 422


def test_unknown_slug_with_a_cursor_is_not_found(client, shop):
    post(client, shop.slug)
    cursor = poll(client, shop.slug)["cursor"]  # a good cursor and map entry, for another slug
    assert_not_found(client.get(messages_url("no-such-slug"), params={"cursor": cursor}))


@pytest.mark.parametrize("path", ["fast", "slow"])
def test_poll_limit_returns_429(client, shop, monkeypatch, path):
    post(client, shop.slug)
    cursor = poll(client, shop.slug)["cursor"]  # poll 1 (slow)
    monkeypatch.setattr(chat_poll, "CHAT_POLL_IP_LIMIT", 2)
    params = {"cursor": cursor} if path == "fast" else {}
    assert client.get(messages_url(shop.slug), params=params).status_code == 200  # poll 2
    response = client.get(messages_url(shop.slug), params=params)  # poll 3
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_polls"
    assert response.json()["error"]["message"] == "Too many requests. Please wait a minute."
    assert int(response.headers["Retry-After"]) > 0


@pytest.mark.parametrize("with_cursor", [True, False], ids=["fast", "slow"])
def test_poll_fails_closed_without_redis(make_client, shop, monkeypatch, with_cursor):
    browser = make_client(raise_server_exceptions=False)
    post(browser, shop.slug)
    cursor = poll(browser, shop.slug)["cursor"]
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # port 1 refuses at once
    get_settings.cache_clear()
    get_redis.cache_clear()
    response = browser.get(messages_url(shop.slug), params={"cursor": cursor} if with_cursor else {})
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "dependency_unavailable",
        "message": "Chat is not available right now. Please try again.",
    }

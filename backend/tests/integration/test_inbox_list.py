# The Inbox list (story 4.3, FR-23): GET /api/v1/inbox/conversations.
# Needs Human first, then newest activity, then id. Pages use a keyset cursor: the sort key of
# the last row shown; the next page starts right after it, so nothing repeats or is skipped.
import uuid
from datetime import UTC, datetime

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from tests.integration.conftest import set_owner_roles
from tests.integration.test_inbox_service import send

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.core.tokens import new_token
from app.modules.inbox.models import Conversation
from app.modules.inbox.repository import ConversationRepository

URL = "/api/v1/inbox/conversations"


def new_chat(business_id: uuid.UUID, body: str = "Fan not working", token: str | None = None) -> uuid.UUID:
    """One new visitor (or this token's) sends one Message. Returns their Conversation id."""
    send(business_id, token or new_token(), body)
    with Session(get_engine()) as session:
        return session.scalars(
            select(Conversation.id)
            .where(Conversation.business_id == business_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(1)
        ).one()


def set_state(conversation_id: uuid.UUID, state: str) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text("UPDATE conversations SET state = :s WHERE id = :c"), {"s": state, "c": conversation_id}
        )


def set_last_message_at(conversation_id: uuid.UUID, at: datetime) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text("UPDATE conversations SET last_message_at = :t WHERE id = :c"), {"t": at, "c": conversation_id}
        )


def page(client, **params) -> dict:
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def ids(answer: dict) -> list[uuid.UUID]:
    return [uuid.UUID(row["conversation_id"]) for row in answer["conversations"]]


def test_newest_activity_first(sign_up_owner):
    # Behaviour: the chat with the newest Message is on top; a new Message lifts a chat up.
    owner, business_id = sign_up_owner()
    token_of_a = new_token()
    a = new_chat(business_id, token=token_of_a)
    b, c = new_chat(business_id), new_chat(business_id)
    assert ids(page(owner)) == [c, b, a]
    send(business_id, token_of_a, "Still not working")  # a's visitor sends again
    assert ids(page(owner)) == [a, c, b]


def test_handoff_pinned_on_top(sign_up_owner):
    # Behaviour: a Needs Human chat comes first, even when it is the oldest.
    owner, business_id = sign_up_owner()
    oldest, newer = new_chat(business_id), new_chat(business_id)
    set_state(oldest, "handoff")
    assert ids(page(owner)) == [oldest, newer]


def test_row_shape(sign_up_owner):
    # Behaviour: each row has the state, a one-line preview and the time; the page has the
    # chat slug (for the empty Inbox's Copy link) and the Business timezone (for the time text).
    owner, business_id = sign_up_owner()
    conversation_id = new_chat(business_id, "Fan not\nworking")
    answer = page(owner)
    [row] = answer["conversations"]
    with Session(get_engine()) as session:
        last_message_at = session.get(Conversation, conversation_id).last_message_at
    assert row == {
        "conversation_id": str(conversation_id),
        "state": "agent",
        "last_message_preview": "Fan not working",
        "last_message_at": last_message_at.isoformat().replace("+00:00", "Z"),
    }
    assert answer["chat_slug"] == owner.get("/api/v1/setup").json()["chat_slug"]
    assert answer["timezone"] == "Asia/Kolkata"
    assert answer["next_cursor"] is None


def test_pages_never_repeat_or_skip(sign_up_owner):
    # Behaviour: paging through 25 chats gives each one exactly once, in the one-call order,
    # even when ALL have the SAME time (only the id breaks the tie, also across page edges)
    # and 2 are Needs Human.
    owner, business_id = sign_up_owner()
    chats = [new_chat(business_id) for _ in range(25)]
    same = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    for conversation_id in chats:
        set_last_message_at(conversation_id, same)
    set_state(chats[3], "handoff")
    set_state(chats[20], "handoff")

    pages, cursor = [], None
    while True:
        answer = page(owner, limit=10, **({} if cursor is None else {"cursor": cursor}))
        pages.append(ids(answer))
        cursor = answer["next_cursor"]
        if cursor is None:
            break
    assert [len(p) for p in pages] == [10, 10, 5]
    assert [i for p in pages for i in p] == ids(page(owner, limit=100))
    assert sorted(ids(page(owner, limit=100))) == sorted(chats)


def test_list_query_uses_the_inbox_index(sign_up_owner):
    # Behaviour: the list query writes 'handoff' as fixed SQL text, so Postgres can use the
    # inbox index even for a prepared (re-used) query; EXPLAIN shows the index.
    _, business_id = sign_up_owner()
    new_chat(business_id)
    seen: list[tuple[str, dict]] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "FROM conversations" in statement:
            seen.append((statement, parameters))

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as session, session.begin(), tenant_scope(business_id):
            ConversationRepository(session).inbox_page(None, 20)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    [(statement, parameters)] = seen
    assert "'handoff'" in statement
    assert "handoff" not in str(parameters)
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL enable_seqscan = off")
        plan = "\n".join(row[0] for row in connection.exec_driver_sql(f"EXPLAIN {statement}", parameters))
    assert "ix_conversations_inbox_order" in plan


def test_bad_cursor_is_422(sign_up_owner):
    owner, _ = sign_up_owner()
    response = owner.get(URL, params={"cursor": "junk"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_cursor"


def test_limit_out_of_range_is_422(sign_up_owner):
    owner, _ = sign_up_owner()
    for limit in (0, 101):
        assert owner.get(URL, params={"limit": limit}).status_code == 422


def test_empty_inbox(sign_up_owner):
    owner, _ = sign_up_owner()
    assert page(owner) == {
        "conversations": [],
        "next_cursor": None,
        "chat_slug": owner.get("/api/v1/setup").json()["chat_slug"],
        "timezone": "Asia/Kolkata",
    }


def test_staff_may_list(sign_up_owner):
    owner, business_id = sign_up_owner()
    new_chat(business_id)
    set_owner_roles(business_id, ["staff"])
    assert len(page(owner)["conversations"]) == 1


def test_technician_gets_403(sign_up_owner):
    # Behaviour: a Technician-only User may not use the Inbox (FR-10).
    owner, business_id = sign_up_owner()
    set_owner_roles(business_id, ["technician"])
    response = owner.get(URL)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

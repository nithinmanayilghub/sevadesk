# Integration tests: the migration history is linear and every migration can be undone.
import re
import uuid
from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from tests.integration.conftest import ALEMBIC_INI

from app.core.db import get_engine


def test_alembic_has_one_head():
    # Behaviour: the migration history never splits into two branches.
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1


def test_migrations_downgrade_to_base_and_back(client):
    # Behaviour: every migration can be undone, and redoing them restores the app.
    config = Config(str(ALEMBIC_INI))

    command.downgrade(config, "base")
    tables = set(inspect(get_engine()).get_table_names())
    assert tables <= {"alembic_version"}

    command.upgrade(config, "head")
    tables = set(inspect(get_engine()).get_table_names())
    assert tables == {
        "alembic_version",
        "app_meta",
        "businesses",
        "users",
        "sessions",
        "memberships",
        "invites",
        "services",
        "working_hours",
        "closed_days",
        "customers",
        "visitor_tokens",
        "conversations",
        "messages",
        "bookings",
    }

    response = client.get("/api/v1/hello")
    assert response.status_code == 200
    assert response.json()["message"] == "Namaste from SevaDesk"


def test_upgrade_gives_old_businesses_a_slug(migrated_db):
    # Behaviour: a Business made before migration 0008 gets a chat slug too (story 3.3).
    config = Config(str(ALEMBIC_INI))
    command.downgrade(config, "0007")
    with get_engine().begin() as connection:
        connection.execute(text("INSERT INTO businesses (id, name) VALUES (gen_random_uuid(), 'Old Shop')"))

    command.upgrade(config, "head")
    with get_engine().connect() as connection:
        slug = connection.execute(text("SELECT chat_slug FROM businesses WHERE name = 'Old Shop'")).scalar_one()
    assert re.fullmatch(r"chat-[0-9a-f]{6}", slug)


def test_0010_backfills_last_message_at(migrated_db):
    # Behaviour: old Conversations get the time of their newest Message (or, with none, their
    # own created_at), not "now" (story 4.3).
    config = Config(str(ALEMBIC_INI))
    command.downgrade(config, "0009")
    business, customer, token = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with_messages, without_messages = uuid.uuid4(), uuid.uuid4()
    ids = {"b": business, "cu": customer, "t": token, "c1": with_messages, "c2": without_messages}
    with get_engine().begin() as connection:
        connection.execute(
            text("INSERT INTO businesses (id, name, chat_slug) VALUES (:b, 'Old Inbox', 'chat-0ld010')"), ids
        )
        connection.execute(text("INSERT INTO customers (id, business_id) VALUES (:cu, :b)"), ids)
        connection.execute(text("INSERT INTO visitor_tokens (id, business_id, token_hash) VALUES (:t, :b, 'h')"), ids)
        connection.execute(
            text(
                "INSERT INTO conversations (id, business_id, customer_id, visitor_token_id, last_seq, created_at)"
                " VALUES (:c1, :b, :cu, :t, 2, '2025-12-31 10:00+00'),"
                " (:c2, :b, :cu, :t, 0, '2026-03-01 10:00+00')"
            ),
            ids,
        )
        connection.execute(
            text(
                "INSERT INTO messages (id, business_id, conversation_id, seq, author_type, body, lang, created_at)"
                " VALUES (gen_random_uuid(), :b, :c1, 1, 'customer', 'hi', 'en', '2026-01-01 10:00+00'),"
                " (gen_random_uuid(), :b, :c1, 2, 'customer', 'hi', 'en', '2026-01-02 10:00+00')"
            ),
            ids,
        )

    command.upgrade(config, "head")
    with get_engine().connect() as connection:
        rows = dict(
            connection.execute(text("SELECT id, last_message_at FROM conversations WHERE business_id = :b"), ids).all()
        )
    assert rows[with_messages] == datetime(2026, 1, 2, 10, tzinfo=UTC)
    assert rows[without_messages] == datetime(2026, 3, 1, 10, tzinfo=UTC)

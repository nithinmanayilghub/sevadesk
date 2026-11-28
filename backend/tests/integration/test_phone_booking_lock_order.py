# The lock-order tests for the inbox -> bookings flows (AR-23, AD-15): one test per flow.
#
# The rule: when inbox calls bookings, inbox calls bookings FIRST, before it reads or writes
# its own rows. Here that means: the capacity lock comes before any SQL on inbox's tables.
#
# The bug it prevents (phone-in): two phone-ins with the same new phone. If the lookup ran
# before the lock, both would find nobody; the second INSERT would then break the unique phone
# rule (a 500). Worse, T1 holds the new phone row while it waits for the lock, and T2 holds the
# lock while it waits for that row: each waits for the other forever (a deadlock).
# From-chat: one rule for every flow ("capacity lock first") means no two flows can ever take
# the same locks in opposite orders (Story 5.5's Customer delete will take it first too).
import uuid

import pytest
from sqlalchemy import event
from tests.integration.booking_helpers import MON_10, fixed_clock, make_shop
from tests.integration.test_inbox_list import new_chat
from tests.integration.test_phone_booking import PHONE_URL, chat_url, phone_body

from app.core.db import get_engine

pytestmark = pytest.mark.usefixtures("fixed_clock")
__all__ = ["fixed_clock"]  # imported so pytest can find the fixture by name


def _statements_of(post) -> list[str]:
    """Every SQL statement sent while `post()` runs. The listener is always removed again."""
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = post()
    finally:
        event.remove(engine, "before_cursor_execute", record)  # never leak into other tests
    assert response.status_code == 201, response.text
    return statements


def _first(statements: list[str], word: str) -> int:
    return next(i for i, sql in enumerate(statements) if word in sql)


def test_phone_in_takes_the_capacity_lock_before_touching_customers(sign_up_owner):
    owner, _, service_id = make_shop(sign_up_owner)
    statements = _statements_of(lambda: owner.post(PHONE_URL, json=phone_body(service_id)))
    assert _first(statements, "pg_advisory_xact_lock") < _first(statements, "customers"), (
        "inbox touched customers before it took the capacity lock"
    )


def test_from_chat_takes_the_capacity_lock_before_touching_conversations(sign_up_owner):
    owner, business_id, service_id = make_shop(sign_up_owner)
    conversation_id: uuid.UUID = new_chat(business_id)
    body = {"service_id": str(service_id), "starts_at": MON_10.isoformat()}
    statements = _statements_of(lambda: owner.post(chat_url(conversation_id), json=body))
    assert _first(statements, "pg_advisory_xact_lock") < _first(statements, "conversations"), (
        "inbox touched conversations before it took the capacity lock"
    )

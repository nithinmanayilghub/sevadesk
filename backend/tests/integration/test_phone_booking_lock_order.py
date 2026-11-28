# The lock-order test for the phone-in flow (AR-23, AD-15): one test per cross-module flow.
#
# The rule: when inbox calls bookings, inbox calls bookings FIRST, before it reads or writes
# its own rows. Here that means: the capacity lock comes before any SQL on `customers`.
#
# The bug it prevents: two phone-ins with the same new phone. If the lookup ran before the lock,
# both would find nobody; the second INSERT would then break the unique phone rule (a 500).
# Worse, T1 holds the new phone row while it waits for the lock, and T2 holds the lock while it
# waits for that row: each waits for the other forever (a deadlock; Postgres kills one).
import pytest
from sqlalchemy import event
from tests.integration.booking_helpers import fixed_clock, make_shop
from tests.integration.test_phone_booking import PHONE_URL, phone_body

from app.core.db import get_engine

pytestmark = pytest.mark.usefixtures("fixed_clock")
__all__ = ["fixed_clock"]  # imported so pytest can find the fixture by name


def test_phone_in_takes_the_capacity_lock_before_touching_customers(sign_up_owner):
    owner, _, service_id = make_shop(sign_up_owner)
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = owner.post(PHONE_URL, json=phone_body(service_id))
    finally:
        event.remove(engine, "before_cursor_execute", record)  # never leak into other tests
    assert response.status_code == 201, response.text

    lock_at = next(i for i, sql in enumerate(statements) if "pg_advisory_xact_lock" in sql)
    customers_at = next(i for i, sql in enumerate(statements) if "customers" in sql)
    assert lock_at < customers_at, "inbox touched customers before it took the capacity lock"

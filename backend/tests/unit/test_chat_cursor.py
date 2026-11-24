# The poll cursor (story 4.2): the browser keeps it and sends it back; only the server reads it.
import uuid

import pytest

from app.modules.inbox.schemas import ChatCursor

BUSINESS = uuid.UUID("01900000-0000-7000-8000-000000000001")


def test_round_trip():
    cursor = ChatCursor(business_id=BUSINESS, after_seq=7, version=2**33)
    assert cursor.format() == f"v1.{BUSINESS}.7.{2**33}"
    assert ChatCursor.parse(cursor.format()) == cursor


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        f"v2.{BUSINESS}.1.1",  # an unknown format version
        f"v1.{BUSINESS}.1.1\n",  # a trailing new line ($ would let it through; fullmatch does not)
        f"v1.{'-' * 36}.1.1",  # the right length, but not a UUID
        "v1.not-a-uuid.1.1",
        f"v1.{BUSINESS}.-1.1",  # a negative seq
        f"v1.{BUSINESS}.1",  # a part missing
        "x" * 5000,
    ],
    ids=["none", "empty", "v2", "newline", "dashes", "not-uuid", "negative", "missing", "huge"],
)
def test_bad_cursors_are_none(raw):
    assert ChatCursor.parse(raw) is None

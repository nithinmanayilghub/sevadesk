# The Inbox page cursor and the one-line preview (story 4.3). Pure functions: no database.
import uuid
from datetime import UTC, datetime

import pytest

from app.modules.inbox.schemas import InboxCursor, preview

ID = uuid.UUID("0193a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b")


def test_cursor_round_trips():
    # Behaviour: what the server writes, it reads back exactly, down to the microsecond.
    cursor = InboxCursor(
        pinned=True, last_message_at=datetime(2026, 11, 25, 10, 42, 7, 123456, UTC), conversation_id=ID
    )
    assert InboxCursor.parse(cursor.format()) == cursor


@pytest.mark.parametrize(
    "raw",
    ["", f"v2.1.5.{ID}", f"v1.2.5.{ID}", "v1.1.5.not-a-uuid-at-all-but-36-chars-x", f"v1.1.5.{ID}\n", f"v1.1.-5.{ID}"],
)
def test_bad_cursor_is_none(raw):
    # Behaviour: anything the server did not write is refused, never half-read.
    assert InboxCursor.parse(raw) is None


def test_preview_is_one_short_line():
    # Behaviour: the Inbox row shows one line, at most 120 characters (code points).
    assert preview("a\n\n b\tc") == "a b c"
    assert len(preview("क" * 300)) == 120


def test_biggest_cursor_time_does_not_crash():
    # Behaviour: the regex allows at most 17 digits, so the time always fits in a datetime
    # (max year 9999). 18 digits could reach past 9999 and crash with a 500.
    raw = f"v1.0.{'9' * 17}.{ID}"
    cursor = InboxCursor.parse(raw)
    assert cursor is not None
    assert cursor.last_message_at.year == 5138

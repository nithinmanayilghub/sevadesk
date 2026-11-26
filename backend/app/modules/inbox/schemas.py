# Request and response shapes of the public chat routes (story 4.1). The backend owns every
# body rule; the Chat Page shows the message it gets back.
#
# No conversation_id in or out, on purpose (AR-10): a visitor is known only by their cookie,
# so there is no id to guess or swap.
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, field_validator
from pydantic_core import PydanticCustomError

MAX_BODY = 2000  # characters

# Line breaks and tabs are normal in a chat. Every other control character (Cc) is refused.
# So is a lone surrogate (Cs): half of an emoji's code with no other half. JSON allows it,
# but it is not real text, and Postgres cannot store it (a 500 without this check).
_ALLOWED_CONTROL = {"\n", "\r", "\t"}
_REFUSED_CATEGORIES = {"Cc", "Cs"}


def detect_lang(body: str) -> Literal["en", "hi"]:
    """ "hi" when the text has Devanagari letters (U+0900–U+097F), else "en".

    Used for lang="hi" on the Chat Page (UX-DR32), so screen readers and fonts treat the
    text as Hindi. Hindi written in Latin letters (Hinglish) stays "en" for now; the Agent
    stories detect the language properly.
    """
    return "hi" if any("ऀ" <= char <= "ॿ" for char in body) else "en"


class SendMessageIn(BaseModel):
    body: str
    # Made by the browser for each new Message, and sent again on a retry. The server saves
    # one Message per id (idempotent send, AD-8), so a retry never makes a copy.
    client_message_id: uuid.UUID

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        # Checked BEFORE strip: a hidden character at the end must not slip through.
        # Postgres cannot store NUL (\x00): without this check it would be a 500, not a 422.
        if any(unicodedata.category(char) in _REFUSED_CATEGORIES and char not in _ALLOWED_CONTROL for char in value):
            raise PydanticCustomError("message_bad_characters", "This message has characters we cannot save.")
        value = value.strip()
        if not value:
            raise PydanticCustomError("message_empty", "Write a message first.")
        if len(value) > MAX_BODY:
            raise PydanticCustomError("message_too_long", "A message can be at most 2000 characters.")
        return value


class MessageOut(BaseModel):
    """One Message as the Chat Page sees it. No ids except the browser's own client_message_id."""

    seq: int  # 1, 2, 3, … the order inside the Conversation
    author_type: str  # customer | agent | user | system
    body: str
    lang: str  # en | hi
    client_message_id: uuid.UUID | None
    actions: list[dict[str, Any]]  # UI chips; empty until the Agent stories
    created_at: datetime


class ChatSnapshot(BaseModel):
    """The Conversation's state now. Epic 5/6 add reply_pending and the Booking status (AD-7)."""

    conversation_state: str  # agent | handoff | closed


class ChatPollOut(BaseModel):
    """One poll answer (story 4.2). The same shape for the first load and every later poll."""

    changed: bool  # False: nothing new since the cursor; keep what is on screen
    messages: list[MessageOut]  # only the ones after the cursor, oldest first; [] when not changed
    snapshot: ChatSnapshot | None  # None when not changed, or before the first Message
    cursor: str | None  # send it back on the next poll; None before the first Message


# v1.<business_id>.<after_seq>.<version>. fullmatch, not match + $: "$" also accepts a trailing "\n".
_CURSOR_SHAPE = re.compile(r"v1\.([0-9a-f-]{36})\.(\d{1,9})\.(\d{1,15})")


@dataclass(frozen=True)
class ChatCursor:
    """Where a Chat Page is: which Business, the last seq it has, and the version it saw.

    "Opaque" for the browser: it keeps the text and sends it back, and never reads inside.
    Nothing in it is secret or trusted: the server checks it against the cookie (story 4.2).
    No conversation_id inside, on purpose (AR-10).
    """

    business_id: uuid.UUID
    after_seq: int
    version: int

    def format(self) -> str:
        return f"v1.{self.business_id}.{self.after_seq}.{self.version}"

    @classmethod
    def parse(cls, raw: str | None) -> ChatCursor | None:
        """The cursor, or None for anything we did not make (then the poll sends everything)."""
        match = _CURSOR_SHAPE.fullmatch(raw) if raw else None
        if match is None:
            return None
        try:
            business_id = uuid.UUID(match[1])  # 36 dashes fit the shape but are not a UUID
        except ValueError:
            return None
        return cls(business_id=business_id, after_seq=int(match[2]), version=int(match[3]))


# ---------------------------------------------------------------- the Inbox list (story 4.3, FR-23)

PREVIEW_CHARS = 120


def preview(body: str) -> str:
    """A Message as one short line: line breaks and runs of spaces become one space, then cut.

    The cut counts code points, so it never splits one character; it can split a Devanagari
    cluster (क्ष) at the very end, which the screen hides anyway (CSS truncate).
    """
    return " ".join(body.split())[:PREVIEW_CHARS]


class InboxRow(BaseModel):
    """One Conversation in the Inbox list. No name or phone yet: no story has collected them."""

    conversation_id: uuid.UUID
    state: Literal["agent", "handoff", "closed"]  # the badge: Agent / Needs Human / Closed
    last_message_preview: str  # one line, at most PREVIEW_CHARS
    last_message_at: datetime  # sorts the list; shown in the Business timezone


class InboxPage(BaseModel):
    """One page of the Inbox, Needs Human first, then newest activity first."""

    conversations: list[InboxRow]
    next_cursor: str | None  # send it back for the next page; None on the last page
    chat_slug: str  # the empty Inbox's "Copy link" (Staff cannot read /setup)
    timezone: str  # the Business timezone, e.g. "Asia/Kolkata": times show in it (UX-DR4)


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ONE_MICROSECOND = timedelta(microseconds=1)
# v1.<pinned 0|1>.<microseconds since 1970 UTC>.<conversation_id>. fullmatch, like ChatCursor.
_INBOX_CURSOR_SHAPE = re.compile(r"v1\.([01])\.(\d{1,17})\.([0-9a-f-]{36})")


@dataclass(frozen=True)
class InboxCursor:
    """A keyset cursor: the sort key of the last row on a page. The next page starts after it.

    Why not "skip the first 20 rows" (OFFSET)? A new Message moves a chat to the top, so
    every row shifts by one, and OFFSET would show one row twice. A sort key does not shift.
    The time is whole microseconds (an integer), so it round-trips exactly (no float).
    Nothing in it is secret: it only says where to start, inside the User's own Business.
    """

    pinned: bool  # the row was Needs Human
    last_message_at: datetime
    conversation_id: uuid.UUID  # the tie-breaker when two rows have the same time

    def format(self) -> str:
        micros = (self.last_message_at - _EPOCH) // _ONE_MICROSECOND
        return f"v1.{int(self.pinned)}.{micros}.{self.conversation_id}"

    @classmethod
    def parse(cls, raw: str) -> InboxCursor | None:
        """The cursor, or None for anything we did not make."""
        match = _INBOX_CURSOR_SHAPE.fullmatch(raw)
        if match is None:
            return None
        try:
            conversation_id = uuid.UUID(match[3])  # 36 dashes fit the shape but are not a UUID
        except ValueError:
            return None
        return cls(
            pinned=match[1] == "1",
            last_message_at=_EPOCH + int(match[2]) * _ONE_MICROSECOND,
            conversation_id=conversation_id,
        )


class NeedsHumanCount(BaseModel):
    """How many Conversations wait for a human: the red number on the Inbox tab (UX-DR16)."""

    count: int

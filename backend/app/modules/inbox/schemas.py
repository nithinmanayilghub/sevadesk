# Request and response shapes of the public chat routes (story 4.1). The backend owns every
# body rule; the Chat Page shows the message it gets back.
#
# No conversation_id in or out, on purpose (AR-10): a visitor is known only by their cookie,
# so there is no id to guess or swap.
import unicodedata
import uuid
from datetime import datetime
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


class ChatMessagesOut(BaseModel):
    messages: list[MessageOut]  # this visitor's own Conversation only, oldest first

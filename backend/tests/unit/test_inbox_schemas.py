# The send-Message body rules (story 4.1). The API refuses a bad body with a field error (422),
# so nothing odd reaches Postgres: Postgres refuses NUL in text, which would be a 500.
import uuid

import pytest
from pydantic import ValidationError

from app.modules.inbox.schemas import SendMessageIn, detect_lang


def body_error(body: str) -> str:
    with pytest.raises(ValidationError) as caught:
        SendMessageIn(body=body, client_message_id=uuid.uuid4())
    return caught.value.errors()[0]["msg"]


def test_body_is_stripped():
    assert SendMessageIn(body="  Fan not working \n", client_message_id=uuid.uuid4()).body == "Fan not working"


@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
def test_empty_body_is_refused(body):
    assert body_error(body) == "Write a message first."


def test_2000_characters_is_the_limit():
    assert SendMessageIn(body="a" * 2000, client_message_id=uuid.uuid4())
    assert body_error("a" * 2001) == "A message can be at most 2000 characters."


@pytest.mark.parametrize("body", ["hi\u0000", "\u0007ring", "a\u001bb"], ids=["nul", "bell", "escape"])
def test_control_characters_are_refused(body):
    assert body_error(body) == "This message has characters we cannot save."


def test_new_lines_and_tabs_are_fine():
    assert SendMessageIn(body="line 1\nline 2\r\n\ttab", client_message_id=uuid.uuid4())


@pytest.mark.parametrize(
    ("body", "lang"),
    [("नमस्ते, AC kharab hai", "hi"), ("namaste, AC kharab hai", "en"), ("Fan repair please", "en")],
)
def test_detect_lang(body, lang):
    # Devanagari letters mean Hindi. Hindi in Latin letters (Hinglish) is read as "en" for now.
    assert detect_lang(body) == lang

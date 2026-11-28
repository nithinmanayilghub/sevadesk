# The send-Message body rules (story 4.1). The API refuses a bad body with a field error (422),
# so nothing odd reaches Postgres: Postgres refuses NUL in text, which would be a 500.
import uuid

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticCustomError

from app.modules.inbox.schemas import PhoneBookingIn, SendMessageIn, detect_lang, normalize_phone


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


# ---------------------------------------------------------------- phone-in Booking (story 5.2)


@pytest.mark.parametrize("raw", ["98765 43210", "+91-98765-43210", "09876543210", "919876543210", "(98765) 43210"])
def test_normalize_phone(raw):
    # Behaviour: every usual way to write one Indian mobile number gives ONE stored form.
    assert normalize_phone(raw) == "+919876543210"


@pytest.mark.parametrize(
    "raw",
    [
        "12345",  # too short
        "5876543210",  # Indian mobiles start with 6, 7, 8 or 9
        "+1 9876543210",  # not India
        "98765432101",  # 11 digits
        "९८७६५४३२१०",  # Devanagari digits: one phone must never be stored two ways
    ],
)
def test_bad_phone_is_refused(raw):
    with pytest.raises(PydanticCustomError) as caught:
        normalize_phone(raw)
    assert caught.value.message() == "Enter a valid Indian mobile number."


def phone_in(**changes) -> PhoneBookingIn:
    fields = {
        "customer_name": "Asha",
        "customer_phone": "98765 43210",
        "service_id": uuid.uuid4(),
        "starts_at": "2026-11-30T10:00:00+05:30",
    }
    return PhoneBookingIn(**(fields | changes))


def phone_in_error(**changes) -> str:
    with pytest.raises(ValidationError) as caught:
        phone_in(**changes)
    return caught.value.errors()[0]["msg"]


def test_phone_in_body_cleans_name_and_phone():
    body = phone_in(customer_name="  Asha  ")
    assert (body.customer_name, body.customer_phone) == ("Asha", "+919876543210")
    assert body.technician_membership_id is None


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "Enter the customer's name."),
        ("   ", "Enter the customer's name."),
        ("a" * 101, "A name can be at most 100 characters."),
        ("As\x00ha", "This name has characters we cannot save."),
        ("As\nha", "This name has characters we cannot save."),  # a name is one line
    ],
)
def test_customer_name_rules(name, message):
    assert phone_in_error(customer_name=name) == message


def test_bad_phone_message_has_no_prefix():
    # Pydantic adds "Value error, " to a plain ValueError; our message must reach the form as is.
    assert phone_in_error(customer_phone="12345") == "Enter a valid Indian mobile number."


def test_time_without_timezone_is_refused():
    # "10:00" with no zone could be India or UTC: a 5.5-hour mistake. We never guess (AR-5).
    assert phone_in_error(starts_at="2026-11-30T10:00:00").startswith("Input should have timezone info")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"service_id": ""}, "Pick a service."),
        ({"service_id": None}, "Pick a service."),
        ({"starts_at": ""}, "Pick a time."),
        ({"starts_at": None}, "Pick a time."),
    ],
)
def test_empty_service_or_time_says_what_to_pick(changes, message):
    # Regression (story 5.2 review): "Book" before picking showed Pydantic's raw text
    # ("Input should be a valid UUID, invalid length: ..."), which a shop owner cannot read.
    assert phone_in_error(**changes) == message

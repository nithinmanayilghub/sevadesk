# The chat slug rule (story 3.3, FR-14): "<name part>-<6 random chars>".
import pytest

from app.modules.business.chat_slug import SLUG_ALPHABET, make_chat_slug


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ravi Cool Services", "ravi-cool-services"),
        ("  A/C & Fridge!! ", "a-c-fridge"),
        ("Café Cool", "cafe-cool"),  # accents dropped, not the whole letter
        ("सेवा", "chat"),  # no Latin letters at all: a fixed fallback
        ("!!!", "chat"),
        ("x" * 50, "x" * 30),  # cut to 30 chars
        ("a" * 29 + " b", "a" * 29),  # the cut leaves "aaa…-": the trailing "-" goes too
    ],
)
def test_slug_name_part(name, expected):
    slug = make_chat_slug(name)
    assert slug.rsplit("-", 1)[0] == expected


def test_slug_random_part():
    name_part, random_part = make_chat_slug("Ravi").rsplit("-", 1)
    assert name_part == "ravi"
    assert len(random_part) == 6
    assert set(random_part) <= set(SLUG_ALPHABET)


def test_two_slugs_differ():
    assert make_chat_slug("Ravi") != make_chat_slug("Ravi")

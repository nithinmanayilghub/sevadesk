# Unit tests for password rules and hashing.
# - Hashing (story 2.2, D6): NFKC makes one character typed two ways ("é" as one code point,
#   or "e" + a combining accent) count as the same password.
# - New-password rule (story 2.5): one rule for sign-up and invite-accept, owned by accounts.
import pytest
from pydantic_core import PydanticCustomError

from app.modules.accounts.service import check_new_password, hash_password, verify_password


def test_two_unicode_forms_of_one_password_match():
    stored = hash_password("café is open now")  # é as one character
    assert verify_password("café is open now", stored) is True  # e + accent


def test_wrong_password_does_not_match():
    stored = hash_password("correct horse battery")
    assert verify_password("wrong horse battery", stored) is False


def test_new_password_shorter_than_12_is_refused():
    with pytest.raises(PydanticCustomError) as error:
        check_new_password("a" * 11)
    assert error.value.type == "password_short"


def test_new_password_longer_than_128_is_refused():
    with pytest.raises(PydanticCustomError) as error:
        check_new_password("a" * 129)
    assert error.value.type == "password_long"


def test_new_password_keeps_its_spaces():
    # Not stripped: spaces are part of the password.
    assert check_new_password("  twelve chars") == "  twelve chars"

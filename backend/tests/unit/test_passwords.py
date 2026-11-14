# Unit tests for password hashing (story 2.2, D6): NFKC makes one character typed
# two ways ("é" as one code point, or "e" + a combining accent) count as the same password.
from app.modules.accounts.service import hash_password, verify_password


def test_two_unicode_forms_of_one_password_match():
    stored = hash_password("café is open now")  # é as one character
    assert verify_password("café is open now", stored) is True  # e + accent


def test_wrong_password_does_not_match():
    stored = hash_password("correct horse battery")
    assert verify_password("wrong horse battery", stored) is False

# Unit tests for the one email rule that sign-up and log-in share (story 2.2, D7, D8).
import pytest
from pydantic_core import PydanticCustomError

from app.modules.accounts.emails import clean_email


def test_spaces_and_case_are_cleaned():
    assert clean_email("  Owner@Shop.COM ") == "owner@shop.com"


def test_nul_character_is_refused():
    # Postgres cannot store \x00, so it must never reach a query.
    with pytest.raises(PydanticCustomError) as error:
        clean_email("a\x00b@shop.com")
    assert error.value.type == "email_invalid"


def test_too_long_address_is_refused():
    address = "a" * 246 + "@shop.com"  # 255 characters
    with pytest.raises(PydanticCustomError):
        clean_email(address)

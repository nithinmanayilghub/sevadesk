# Unit tests for the one masking function (AD-13): phone numbers and address fields are hidden.
import pytest

from app.core.masking import mask


@pytest.mark.parametrize(
    "text",
    [
        "call 9876543210 now",  # plain 10-digit mobile
        "call +91 98765 43210 now",  # country code, spaces
        "call +91-98765-43210 now",  # country code, hyphens
        "call 098765 43210 now",  # leading 0
        "call 080-2345-6789 now",  # landline with STD code
        "call ९८७६५४३२१० now",  # Devanagari digits
        "call +९१ ९८७६५ ४३२१० now",  # Devanagari with country code
    ],
)
def test_mask_phone_formats(text):
    assert mask(text) == "call [PHONE] now"


@pytest.mark.parametrize(
    "text",
    ["4 items", "year 2026", "pin 560001", "date 2026-11-03", "id 12345678"],
)
def test_mask_leaves_short_numbers(text):
    assert mask(text) == text


def test_mask_address_field_by_key():
    assert mask("12 MG Road", key="address") == "[MASKED]"
    assert mask("12 MG Road", key="customer.home_address") == "[MASKED]"
    assert mask("12 MG Road", key="Address") == "[MASKED]"
    assert mask(None, key="address") is None


def test_mask_nested_structures():
    data = {"address": "12 MG Road", "notes": ["ring 9876543210"], "count": 3}
    assert mask(data) == {"address": "[MASKED]", "notes": ["ring [PHONE]"], "count": 3}


def test_mask_keeps_tuple_type():
    assert mask(("ring 9876543210", 5)) == ("ring [PHONE]", 5)


def test_mask_leaves_hex_ids():
    # Digits inside an ID (letters on either side) are not a phone number.
    assert mask("id 3f9876543210ab") == "id 3f9876543210ab"
    assert mask("ref:9876543210") == "ref:[PHONE]"

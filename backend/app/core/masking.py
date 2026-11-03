# The ONE masking function (AD-13, NFR-8). Logs, spans, and exports all pass through mask().
# It hides Indian phone numbers in text, and the whole value of any field named like "address".
import re

PHONE_PLACEHOLDER = "[PHONE]"
FIELD_PLACEHOLDER = "[MASKED]"

# One digit: Latin 0-9 or Devanagari ०-९ (U+0966 to U+096F).
# We list them on purpose; we do not use \d, which also matches many other scripts.
_DIGIT = "[0-9०-९]"

# A phone number is:
#   (?<!DIGIT)          - not stuck to a digit on the left
#   \+?                 - an optional "+" (as in +91)
#   DIGIT(?:[ -]?DIGIT){9,12}
#                       - 10 to 13 digits; one space or hyphen may sit between two digits
#   (?!DIGIT)           - not stuck to a digit on the right
# 10 digits = a mobile number; up to 13 covers +91, a leading 0, and landlines with an STD code.
# Shorter numbers (dates, PIN codes, counts) are left alone.
_PHONE_RE = re.compile(rf"(?<!{_DIGIT})\+?{_DIGIT}(?:[ -]?{_DIGIT}){{9,12}}(?!{_DIGIT})")


def mask(value: object, key: str | None = None) -> object:
    """Return a copy of value with personal data hidden. key is the field name, if any."""
    # A field named like "address" (e.g. "home_address") is hidden completely.
    if key is not None and "address" in key.lower() and value is not None:
        return FIELD_PLACEHOLDER
    if isinstance(value, str):
        return _PHONE_RE.sub(PHONE_PLACEHOLDER, value)
    if isinstance(value, dict):
        # Each value is checked with its own key.
        return {k: mask(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        # Items in a list share the parent's key; keep the same type (list or tuple).
        return type(value)(mask(item, key=key) for item in value)
    # Numbers, None, booleans, and other types are returned unchanged.
    return value

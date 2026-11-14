# The one email rule (story 2.2, D8). Sign-up and log-in both clean emails here,
# so "Owner@Shop.com " and "owner@shop.com" are always the same account.
import re

from pydantic_core import PydanticCustomError

# A simple shape check: something@something.something, with no spaces and no NUL (\x00).
# Postgres cannot store NUL, so letting it through would crash the query (D7).
_EMAIL_RE = re.compile(r"^[^@\s\x00]+@[^@\s\x00]+\.[^@\s\x00]+$")
MAX_EMAIL = 254


def clean_email(value: str) -> str:
    """Strip and lowercase an email, then check its shape. Raises a field error if bad."""
    value = value.strip().lower()
    if len(value) > MAX_EMAIL or not _EMAIL_RE.match(value):
        raise PydanticCustomError("email_invalid", "Enter a valid email address.")
    return value

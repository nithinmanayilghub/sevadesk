# The chat slug (story 3.3, FR-14): the last part of the public Chat Page link /c/{slug}.
# Shape: "<name part>-<6 random chars>", e.g. "Ravi Cool Services" -> "ravi-cool-services-k7m2qx".
# - The name part makes the link readable when an Owner shares it on WhatsApp.
# - The random part keeps it unique, and stops anyone guessing other Businesses' links.
# Made once at sign-up and never changed, so a shared link keeps working.
import re
import secrets
import unicodedata

# No i, l, o, 0, 1: they look alike, and Owners may read the link aloud.
SLUG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_RANDOM_LENGTH = 6
_MAX_NAME_PART = 30
_NOT_SLUG_TEXT = re.compile(r"[^a-z0-9]+")  # every run of other characters becomes one "-"


def make_chat_slug(name: str) -> str:
    # NFKD splits "é" into "e" + an accent mark; dropping the marks keeps the "e".
    letters = unicodedata.normalize("NFKD", name)
    letters = "".join(char for char in letters if not unicodedata.combining(char))
    name_part = _NOT_SLUG_TEXT.sub("-", letters.lower()).strip("-")
    # Strip again after the cut: it may end on a "-".
    name_part = name_part[:_MAX_NAME_PART].strip("-") or "chat"  # e.g. a Hindi-only name
    random_part = "".join(secrets.choice(SLUG_ALPHABET) for _ in range(_RANDOM_LENGTH))
    return f"{name_part}-{random_part}"

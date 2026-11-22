# The shared secret-token helpers (core/tokens.py): sessions, invites, and chat visitors use them.
import hashlib
import re

from app.core.tokens import hash_token, new_token

# token_urlsafe(32): 32 random bytes in URL-safe base64 = exactly 43 characters.
TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_-]{43}")


def test_new_tokens_differ():
    first, second = new_token(), new_token()
    assert first != second
    assert TOKEN_SHAPE.fullmatch(first)
    assert TOKEN_SHAPE.fullmatch(second)


def test_hash_is_sha256_hex():
    assert hash_token("abc") == hashlib.sha256(b"abc").hexdigest()

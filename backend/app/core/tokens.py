# Secret tokens: the one way to make and hash them. Used for session cookies (AD-5),
# invite links (story 2.5), and Chat Page visitor cookies (AD-16, story 4.1).
#
# The browser (or the invite email) keeps the raw token. The database keeps only its hash,
# so a leaked database backup gives no working cookie or link.
import hashlib
import secrets


def new_token() -> str:
    # 32 random bytes from the OS, as 43 URL-safe characters: impossible to guess.
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # SHA-256 is enough here (no Argon2): the token is 32 random bytes, not a guessable password.
    return hashlib.sha256(token.encode()).hexdigest()

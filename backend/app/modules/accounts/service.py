# The accounts front door (AD-2): other modules call only these functions.
# accounts owns users, sessions, and memberships, so all password logic lives here.
import hashlib
import secrets
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, FieldError
from app.core.tenancy import session_lookup, system_scope

# "as clean_email" marks a re-export: other modules clean emails through this front door (D8).
from app.modules.accounts.emails import clean_email as clean_email
from app.modules.accounts.models import Membership
from app.modules.accounts.repository import MembershipRepository, SessionRepository, UserRepository
from app.modules.accounts.schemas import Actor, OwnerCreated, Role

# A session with no request for this long is refused (D1).
SESSION_IDLE_TIMEOUT = timedelta(days=7)
# last_seen_at is updated at most this often, so not every request writes to the DB (D2).
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)

# Argon2id with pwdlib's recommended settings. Each hash has its own random salt.
_password_hash = PasswordHash((Argon2Hasher(),))

EMAIL_TAKEN_MESSAGE = "An account with this email already exists."


class EmailTaken(AppError):
    def __init__(self):
        super().__init__(
            code="email_taken",
            message=EMAIL_TAKEN_MESSAGE,
            status_code=409,
            fields=[FieldError(field="email", message=EMAIL_TAKEN_MESSAGE)],
        )


class NotAuthenticated(AppError):
    def __init__(self):
        super().__init__(code="not_authenticated", message="Please log in.", status_code=401)


def _normalize(plain: str) -> str:
    # NFKC: one character typed two ways ("é", or "e" + accent) becomes one form (D6).
    return unicodedata.normalize("NFKC", plain)


def hash_password(plain: str) -> str:
    return _password_hash.hash(_normalize(plain))


def verify_password(plain: str, password_hash: str) -> bool:
    return _password_hash.verify(_normalize(plain), password_hash)


def _is_email_unique_violation(error: IntegrityError) -> bool:
    # psycopg tells us which constraint failed. The name comes from migration 0003.
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == "uq_users_email"


def create_owner(session: Session, email: str, password: str) -> OwnerCreated:
    """Create the first User of a new Business, with Roles owner + technician.

    The caller sets tenant_scope to the new Business. No commit here (AD-15).
    """
    users = UserRepository(session)
    # The only cross-Business lookup in sign-up, so the only part in system scope (AD-3).
    with system_scope("signup"):
        if users.email_exists(email):
            raise EmailTaken()

    # Hash only after the check, so a taken email costs no Argon2 work.
    password_hash = hash_password(password)
    try:
        user = users.add(email, password_hash)
    except IntegrityError as error:
        # Two sign-ups with one email at the same moment: the unique index refuses one.
        if _is_email_unique_violation(error):
            raise EmailTaken() from None
        raise

    roles = {Role.OWNER, Role.TECHNICIAN}
    membership = MembershipRepository(session).add(Membership(user_id=user.id, roles=sorted(roles)))
    return OwnerCreated(user_id=user.id, membership_id=membership.id, roles=roles)


# ---------------------------------------------------------------- sessions (AD-5)


def _hash_token(token: str) -> str:
    # The DB keeps only this hash. A leaked DB backup then gives no working cookies.
    # SHA-256 is enough here (no Argon2): the token is 32 random bytes, not a guessable password.
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(session: Session, user_id: uuid.UUID) -> str:
    """Create a session row and return the raw token for the cookie. No commit here (AD-15)."""
    token = secrets.token_urlsafe(32)  # 32 random bytes from the OS: impossible to guess
    SessionRepository(session).add(user_id, _hash_token(token))
    return token


def resolve_session(session: Session, token: str | None) -> Actor:
    """Turn a cookie token into the Actor making the request, or raise NotAuthenticated."""
    if not token:
        raise NotAuthenticated()
    row = SessionRepository(session).get_by_token_hash(_hash_token(token))
    if row is None:
        raise NotAuthenticated()

    now = datetime.now(UTC)
    # An idle session is only refused, not deleted: raising rolls this transaction back,
    # so a delete here would be lost anyway.
    if now - row.last_seen_at > SESSION_IDLE_TIMEOUT:
        raise NotAuthenticated()

    # We look up the membership to learn the Business, so there is no tenant yet (AD-3 (a)).
    with session_lookup():
        membership = MembershipRepository(session).find_for_user(row.user_id)
    if membership is None or not membership.is_active:
        raise NotAuthenticated()

    if now - row.last_seen_at > SESSION_TOUCH_INTERVAL:
        row.last_seen_at = now  # saved when the request's transaction commits

    return Actor(
        user_id=row.user_id,
        membership_id=membership.id,
        business_id=membership.business_id,
        roles={Role(role) for role in membership.roles},
    )


def end_session(session: Session, token: str | None) -> None:
    """Delete the session at once (log-out). A missing or unknown token is not an error."""
    if token:
        SessionRepository(session).delete_by_token_hash(_hash_token(token))

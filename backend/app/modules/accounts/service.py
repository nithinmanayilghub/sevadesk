# The accounts front door (AD-2): other modules call only these functions.
# accounts owns users, sessions, and memberships, so all password logic lives here.
import hashlib
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, FieldError
from app.core.rate_limit import AttemptLimiter
from app.core.redis_client import get_redis
from app.core.tenancy import session_lookup, system_scope, tenant_scope

# "as hash_token" marks a re-export: team.py and tests reach it as accounts service.hash_token.
from app.core.tokens import hash_token as hash_token
from app.core.tokens import new_token

# "as clean_email" marks a re-export: other modules clean emails through this front door (D8).
from app.modules.accounts.emails import clean_email as clean_email
from app.modules.accounts.models import Invite, Membership

# Role checks (FR-10), re-exported the same way: other modules call accounts_service.require_roles.
from app.modules.accounts.permissions import assigned_bookings_filter as assigned_bookings_filter
from app.modules.accounts.permissions import permissions_for as permissions_for
from app.modules.accounts.permissions import require_roles as require_roles
from app.modules.accounts.repository import InviteRepository, MembershipRepository, SessionRepository, UserRepository

# The new-password rule, re-exported: business checks sign-up passwords through this front door.
from app.modules.accounts.schemas import Actor, InvitePreview, OwnerCreated, Role, Theme
from app.modules.accounts.schemas import check_new_password as check_new_password

# A session with no request for this long is refused (D1).
SESSION_IDLE_TIMEOUT = timedelta(days=7)
# last_seen_at is updated at most this often, so not every request writes to the DB (D2).
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)

# Log-in tries before a 15-minute lock (D3): per account, and per client IP.
LOGIN_ACCOUNT_LIMIT = 5
LOGIN_IP_LIMIT = 20
LOGIN_LOCK_SECONDS = 900
_LOGIN_UNAVAILABLE = "Log-in is not available right now. Please try again."

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


class InvalidCredentials(AppError):
    # One message for "no such email" and "wrong password", so replies do not reveal
    # which emails have accounts (user enumeration).
    def __init__(self):
        super().__init__(code="invalid_credentials", message="Wrong email or password.", status_code=401)


class TooManyAttempts(AppError):
    def __init__(self, retry_after: int):
        super().__init__(
            code="too_many_attempts",
            message="Too many tries. Please wait 15 minutes and try again.",
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )


def _normalize(plain: str) -> str:
    # NFKC: one character typed two ways ("é", or "e" + accent) becomes one form (D6).
    return unicodedata.normalize("NFKC", plain)


def hash_password(plain: str) -> str:
    return _password_hash.hash(_normalize(plain))


def verify_password(plain: str, password_hash: str) -> bool:
    return _password_hash.verify(_normalize(plain), password_hash)


# A real Argon2 hash of a password nobody uses. Log-in checks against it when the email
# is unknown, so that case costs the same time as a wrong password (no timing leak).
_DUMMY_HASH = hash_password("no user has this password")


def _is_email_unique_violation(error: IntegrityError) -> bool:
    # psycopg tells us which constraint failed. The name comes from migration 0003.
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == "uq_users_email"


def create_owner(session: Session, email: str, password: str) -> OwnerCreated:
    """Create the first User of a new Business, with Roles owner + technician.

    The caller sets tenant_scope to the new Business. No commit here (AD-15).
    """
    roles = {Role.OWNER, Role.TECHNICIAN}
    membership = _create_user(session, email, password, roles, caller="signup")
    return OwnerCreated(user_id=membership.user_id, membership_id=membership.id, roles=roles)


def _create_user(session: Session, email: str, password: str, roles: set[Role], caller: str) -> Membership:
    """Make a User and their membership in the current Business. Used by sign-up and invite-accept.

    Runs inside the caller's tenant_scope. `caller` names the audited system_scope for the
    email check. No commit here (AD-15).
    """
    users = UserRepository(session)
    # The only cross-Business lookup here, so the only part in system scope (AD-3).
    with system_scope(caller):
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

    return MembershipRepository(session).add(Membership(user_id=user.id, roles=sorted(roles)))


# ---------------------------------------------------------------- sessions (AD-5)


def start_session(session: Session, user_id: uuid.UUID) -> str:
    """Create a session row and return the raw token for the cookie. No commit here (AD-15)."""
    token = new_token()  # the DB keeps only hash_token(token)
    SessionRepository(session).add(user_id, hash_token(token))
    return token


def resolve_session(session: Session, token: str | None) -> Actor:
    """Turn a cookie token into the Actor making the request, or raise NotAuthenticated."""
    if not token:
        raise NotAuthenticated()
    row = SessionRepository(session).get_by_token_hash(hash_token(token))
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
        # A direct UPDATE: if this session was deleted meanwhile, it changes nothing (no 500).
        SessionRepository(session).touch(row.id, now)

    return _actor(membership)


def _actor(membership: Membership) -> Actor:
    return Actor(
        user_id=membership.user_id,
        membership_id=membership.id,
        business_id=membership.business_id,
        roles={Role(role) for role in membership.roles},
    )


def end_session(session: Session, token: str | None) -> None:
    """Delete the session at once (log-out). A missing or unknown token is not an error."""
    if token:
        SessionRepository(session).delete_by_token_hash(hash_token(token))


# ---------------------------------------------------------------- log-in (FR-8, NFR-5)


def _login_limiters() -> tuple[AttemptLimiter, AttemptLimiter]:
    redis = get_redis()
    return (
        AttemptLimiter(redis, "login_fail:acct", LOGIN_ACCOUNT_LIMIT, LOGIN_LOCK_SECONDS, _LOGIN_UNAVAILABLE),
        AttemptLimiter(redis, "login_fail:ip", LOGIN_IP_LIMIT, LOGIN_LOCK_SECONDS, _LOGIN_UNAVAILABLE),
    )


def log_in(session: Session, email: str, password: str, ip: str) -> tuple[str, Actor]:
    """Check the password and start a session. Returns (token, Actor). No commit here (AD-15).

    `email` must already be cleaned (LoginRequest does it). `ip` comes from core.client_ip.
    """
    account_limiter, ip_limiter = _login_limiters()
    # The key is a hash of the email: Redis never holds the email itself.
    account_key = hashlib.sha256(email.encode()).hexdigest()

    # Count first (D3): this try is counted before the slow password check, so
    # many tries at the same moment cannot all slip past a count of 0.
    waits = [wait for wait in (account_limiter.hit(account_key), ip_limiter.hit(ip)) if wait is not None]
    if waits:
        raise TooManyAttempts(retry_after=max(waits))

    # Finding a user by email searches every Business: an audited system lookup (AD-3).
    with system_scope("login"):
        user = UserRepository(session).get_by_email(email)
        membership = MembershipRepository(session).find_for_user(user.id) if user else None

    # Always exactly one Argon2 check, even for an unknown email (same time either way).
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not (password_ok and membership and membership.is_active):
        raise InvalidCredentials()  # this try stays counted

    # Success: forget this account's failures, and do not count this try against the IP.
    account_limiter.clear(account_key)
    ip_limiter.undo(ip)
    return start_session(session, user.id), _actor(membership)


# ---------------------------------------------------------------- invite accept (FR-9, AD-3)


class InviteInvalid(AppError):
    # One answer for unknown, used, and expired: a caller learns nothing about which it was.
    def __init__(self):
        super().__init__(code="invite_invalid", message="This invite is no longer valid.", status_code=404)


def _valid_invite(session: Session, token: str, *, lock: bool) -> Invite:
    """The invite for this raw token, or InviteInvalid. lock=True holds the row until commit."""
    # The invited person has no session: finding the invite searches every Business (AD-3 (d)).
    with system_scope("invite_accept"):
        invite = InviteRepository(session).find_by_token_hash(hash_token(token), lock=lock)
    if invite is None or invite.used_at is not None or datetime.now(UTC) >= invite.expires_at:
        raise InviteInvalid()
    return invite


def preview_invite(session: Session, token: str) -> InvitePreview:
    """Who is invited. A read only, so it takes no lock."""
    return InvitePreview(email=_valid_invite(session, token, lock=False).email)


def accept_invite(session: Session, token: str, password: str) -> tuple[str, Actor]:
    """Make the invited User and membership, mark the invite used, and log in. Returns (token, Actor).

    The row lock makes a second accept of the same invite wait; it then sees used_at and fails.
    No commit here (AD-15): if any step fails, the whole request rolls back, invite included.
    """
    invite = _valid_invite(session, token, lock=True)
    # The tenant is server-derived: it comes from the invite row the secret token found.
    with tenant_scope(invite.business_id):
        roles = {Role(role) for role in invite.roles}
        membership = _create_user(session, invite.email, password, roles, caller="invite_accept")
    # Only after the User exists: an EmailTaken above leaves the invite unused.
    invite.used_at = datetime.now(UTC)
    return start_session(session, membership.user_id), _actor(membership)


# ---------------------------------------------------------------- team (AR-7)


def active_technician_ids(session: Session) -> list[uuid.UUID]:
    """The membership ids of the active Technicians in the current Business, oldest first.

    The ONE place that says who counts as an active Technician (AR-7). Bookings use it later
    to assign jobs. Runs inside a tenant_scope.
    """
    return MembershipRepository(session).active_technician_ids()


def get_theme(session: Session, user_id: uuid.UUID) -> Theme:
    return UserRepository(session).get_theme(user_id)


def set_theme(session: Session, user_id: uuid.UUID, theme: Theme) -> None:
    # No commit here: the request commits (AD-15).
    UserRepository(session).set_theme(user_id, theme)

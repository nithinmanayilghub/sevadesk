# The accounts front door (AD-2): other modules call only these functions.
# accounts owns users, sessions, and memberships, so all password logic lives here.
import unicodedata

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, FieldError
from app.core.tenancy import system_scope

# "as clean_email" marks a re-export: other modules clean emails through this front door (D8).
from app.modules.accounts.emails import clean_email as clean_email
from app.modules.accounts.models import Membership
from app.modules.accounts.repository import MembershipRepository, UserRepository
from app.modules.accounts.schemas import OwnerCreated, Role

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

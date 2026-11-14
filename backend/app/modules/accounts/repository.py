# Database access for accounts. Only accounts/service.py uses this file (AD-2).
import uuid

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.core.repository import TenantRepository
from app.core.tenancy import require_system_scope
from app.modules.accounts.models import Membership, User, UserSession


class UserRepository:
    # users is a global table, so there is no tenant filter here.
    def __init__(self, session: Session):
        self.session = session

    def email_exists(self, email: str) -> bool:
        # A lookup across all Businesses' users: allowed only in audited system scope (AD-3).
        require_system_scope()
        return self.session.scalar(select(exists().where(User.email == email)))

    def add(self, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self.session.add(user)
        self.session.flush()  # fills user.id; a duplicate email fails here
        return user


class SessionRepository:
    # sessions is a global table: a session is found by its token before we know the Business.
    def __init__(self, session: Session):
        self.session = session

    def add(self, user_id: uuid.UUID, token_hash: str) -> UserSession:
        row = UserSession(user_id=user_id, token_hash=token_hash)
        self.session.add(row)
        self.session.flush()
        return row

    def get_by_token_hash(self, token_hash: str) -> UserSession | None:
        return self.session.scalars(select(UserSession).where(UserSession.token_hash == token_hash)).one_or_none()

    def delete_by_token_hash(self, token_hash: str) -> None:
        self.session.execute(delete(UserSession).where(UserSession.token_hash == token_hash))


class MembershipRepository(TenantRepository[Membership]):
    model = Membership

    def find_for_user(self, user_id: uuid.UUID) -> Membership | None:
        # The one tenant-table query without the tenant filter: we look up the membership
        # to LEARN the Business. Allowed only in session_lookup / system scope (AD-3).
        require_system_scope()
        return self.session.scalars(select(Membership).where(Membership.user_id == user_id)).one_or_none()

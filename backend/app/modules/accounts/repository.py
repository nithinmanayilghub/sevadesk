# Database access for accounts. Only accounts/service.py uses this file (AD-2).
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.repository import TenantRepository
from app.core.tenancy import require_system_scope
from app.modules.accounts.models import Membership, User


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


class MembershipRepository(TenantRepository[Membership]):
    model = Membership

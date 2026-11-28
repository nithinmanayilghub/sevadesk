# Database access for accounts. Only accounts' own files use it (service.py, team.py); other modules never do (AD-2).
import uuid
from datetime import datetime

from sqlalchemy import delete, exists, select, update
from sqlalchemy.orm import Session

from app.core.repository import TenantRepository
from app.core.tenancy import require_system_scope
from app.modules.accounts.models import Invite, Membership, User, UserSession
from app.modules.accounts.schemas import Theme


class UserRepository:
    # users is a global table, so there is no tenant filter here.
    def __init__(self, session: Session):
        self.session = session

    def email_exists(self, email: str) -> bool:
        # A lookup across all Businesses' users: allowed only in audited system scope (AD-3).
        require_system_scope()
        return self.session.scalar(select(exists().where(User.email == email)))

    def get_by_email(self, email: str) -> User | None:
        # Log-in looks a user up across all Businesses: system scope only (AD-3).
        require_system_scope()
        return self.session.scalars(select(User).where(User.email == email)).one_or_none()

    def add(self, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self.session.add(user)
        self.session.flush()  # fills user.id; a duplicate email fails here
        return user

    def get_theme(self, user_id: uuid.UUID) -> Theme:
        # Reads only the caller's own row, so no system scope is needed.
        return Theme(self.session.scalars(select(User.theme).where(User.id == user_id)).one())

    def set_theme(self, user_id: uuid.UUID, theme: Theme) -> None:
        # Writes only the caller's own row.
        self.session.execute(update(User).where(User.id == user_id).values(theme=theme.value))


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

    def delete_for_user(self, user_id: uuid.UUID) -> None:
        # Log a User out everywhere at once (deactivation, AD-5).
        self.session.execute(delete(UserSession).where(UserSession.user_id == user_id))

    def touch(self, session_id: uuid.UUID, now: datetime) -> None:
        # One direct UPDATE, not a change on the loaded row: if the row was deleted meanwhile
        # (the member was just deactivated), this changes 0 rows instead of crashing.
        self.session.execute(update(UserSession).where(UserSession.id == session_id).values(last_seen_at=now))


class MembershipRepository(TenantRepository[Membership]):
    model = Membership

    def find_for_user(self, user_id: uuid.UUID) -> Membership | None:
        # The one tenant-table query without the tenant filter: we look up the membership
        # to LEARN the Business. Allowed only in session_lookup / system scope (AD-3).
        require_system_scope()
        return self.session.scalars(select(Membership).where(Membership.user_id == user_id)).one_or_none()

    def list_with_emails(self) -> list[tuple[Membership, str]]:
        # Every member of the current Business with their email, oldest first.
        query = (
            self._select()  # the tenant filter
            .add_columns(User.email)
            .join(User, User.id == Membership.user_id)
            .order_by(Membership.created_at, Membership.id)
        )
        return [(membership, email) for membership, email in self.session.execute(query)]

    def _active_technicians(self):
        # THE rule (AR-7): active members of the current Business that hold the Technician Role,
        # oldest first. Both methods below start here, so the rule is written once.
        return (
            self._select()
            .where(Membership.is_active, Membership.roles.contains(["technician"]))
            .order_by(Membership.created_at, Membership.id)
        )

    def active_technician_ids(self) -> list[uuid.UUID]:
        return [membership.id for membership in self.session.scalars(self._active_technicians())]

    def active_technicians_with_emails(self) -> list[tuple[uuid.UUID, str]]:
        """(membership id, email) of each active Technician, for the booking form's picker."""
        query = self._active_technicians().add_columns(User.email).join(User, User.id == Membership.user_id)
        return [(membership.id, email) for membership, email in self.session.execute(query)]


class InviteRepository(TenantRepository[Invite]):
    # The base class adds the tenant filter and sets business_id on add (AD-3).
    model = Invite

    def find_by_token_hash(self, token_hash: str, *, lock: bool) -> Invite | None:
        # The invited person has no session, so we look the invite up to LEARN the Business:
        # no tenant filter, so system scope only (AD-3). lock=True adds FOR UPDATE: a second
        # accept of the same invite then waits until the first one commits.
        require_system_scope()
        query = select(Invite).where(Invite.token_hash == token_hash)
        if lock:
            query = query.with_for_update()
        return self.session.scalars(query).one_or_none()

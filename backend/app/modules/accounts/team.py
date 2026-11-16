# Owner actions on the team (story 2.5, FR-9, FR-10): invite people, and (Task 5) manage members.
# Every function checks the Role FIRST, before it reads or changes anything (story 2.4).
# Only accounts' own team_router calls this file. service.py must never import it
# (this file imports service.py, so the other way round would be an import cycle).
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.modules.accounts import service
from app.modules.accounts.models import Invite
from app.modules.accounts.repository import InviteRepository
from app.modules.accounts.schemas import Actor, InviteCreated, InviteRequest, Permission

# FR-9: an invite link expires after 7 days.
INVITE_LIFETIME = timedelta(days=7)


def create_invite(session: Session, actor: Actor, request: InviteRequest) -> InviteCreated:
    """Make a single-use invite link. Returns the raw token once. No commit here (AD-15)."""
    service.require_roles(actor, Permission.MANAGE_SETUP)
    token = secrets.token_urlsafe(32)  # 32 random bytes from the OS, like a session token
    expires_at = datetime.now(UTC) + INVITE_LIFETIME
    InviteRepository(session).add(
        Invite(
            email=request.email,
            roles=[str(role) for role in request.roles],
            token_hash=service.hash_token(token),
            expires_at=expires_at,
        )
    )
    return InviteCreated(token=token, expires_at=expires_at)

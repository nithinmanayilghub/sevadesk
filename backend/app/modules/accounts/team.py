# Owner actions on the team (story 2.5, FR-9, FR-10): invite people, list and manage members.
# Every function checks the Role FIRST, before it reads or changes anything (story 2.4).
# Only accounts' own team_router calls this file. service.py must never import it
# (this file imports service.py, so the other way round would be an import cycle).
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import AppError, FieldError
from app.modules.accounts import service
from app.modules.accounts.models import Invite
from app.modules.accounts.repository import InviteRepository, MembershipRepository, SessionRepository
from app.modules.accounts.schemas import (
    Actor,
    InviteCreated,
    InviteRequest,
    MemberUpdate,
    Permission,
    Role,
    TeamMember,
    TeamResponse,
)

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


class TeamRuleBroken(AppError):
    """422: the change would break a team rule (e.g. an Owner deactivating themself)."""

    def __init__(self, field: str, message: str):
        super().__init__(
            code="validation_error",
            message="Some fields need fixing.",
            status_code=422,
            fields=[FieldError(field=field, message=message)],
        )


def list_team(session: Session, actor: Actor) -> TeamResponse:
    """Every member of the Owner's Business, oldest first, and whether it is "just you"."""
    service.require_roles(actor, Permission.MANAGE_SETUP)
    members = [
        TeamMember(
            membership_id=membership.id,
            email=email,
            roles=sorted(Role(role) for role in membership.roles),
            is_active=membership.is_active,
            is_you=membership.id == actor.membership_id,
        )
        for membership, email in MembershipRepository(session).list_with_emails()
    ]
    just_you = service.active_technician_ids(session) == [actor.membership_id]
    return TeamResponse(members=members, just_you=just_you)


def update_member(session: Session, actor: Actor, membership_id: uuid.UUID, change: MemberUpdate) -> TeamResponse:
    """Change a member's Roles, or deactivate / reactivate them. Never deletes a membership (AD-4)."""
    # Role check FIRST: a 403 then says nothing about whether this id exists (story 2.4).
    service.require_roles(actor, Permission.MANAGE_SETUP)
    # The tenant filter hides other Businesses' members: their ids answer 404 (FR-11).
    row = MembershipRepository(session).get_or_raise(membership_id)

    # MVP: one Owner per Business. Nobody gets or loses the Owner Role here.
    if change.roles is not None and (Role.OWNER in change.roles) != (Role.OWNER in row.roles):
        raise TeamRuleBroken("roles", "The Owner Role can't be changed.")
    # Else nobody would be left to manage the Business.
    if change.is_active is False and row.id == actor.membership_id:
        raise TeamRuleBroken("is_active", "You can't deactivate yourself.")

    if change.roles is not None:
        row.roles = [str(role) for role in change.roles]
    if change.is_active is not None:
        row.is_active = change.is_active
        if not change.is_active:
            # Logged out everywhere, at once (AD-5). Their next request gets 401.
            SessionRepository(session).delete_for_user(row.user_id)
    session.flush()  # send the changes now, so the list below reads them
    return list_team(session, actor)

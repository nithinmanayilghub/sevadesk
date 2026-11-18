# HTTP routes for Settings → Team (story 2.5): Owner actions only. The Role check lives in team.py.
import uuid

from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.errors import ErrorEnvelope
from app.modules.accounts import team
from app.modules.accounts.dependencies import ActorDep
from app.modules.accounts.schemas import InviteCreated, InviteRequest, MemberUpdate, TeamResponse

router = APIRouter(prefix="/api/v1")

# Listed so the OpenAPI schema (and so the frontend types) know the error shape.
_ERROR = {"model": ErrorEnvelope}


@router.post(
    "/team/invites",
    status_code=201,
    operation_id="create_invite",
    responses={401: _ERROR, 403: _ERROR, 422: _ERROR},
)
def create_invite(body: InviteRequest, session: SessionDep, actor: ActorDep) -> InviteCreated:
    return team.create_invite(session, actor, body)


@router.get("/team", operation_id="list_team", responses={401: _ERROR, 403: _ERROR})
def list_team(session: SessionDep, actor: ActorDep) -> TeamResponse:
    return team.list_team(session, actor)


@router.patch(
    "/team/members/{membership_id}",
    operation_id="update_member",
    responses={401: _ERROR, 403: _ERROR, 404: _ERROR, 422: _ERROR},
)
def update_member(membership_id: uuid.UUID, body: MemberUpdate, session: SessionDep, actor: ActorDep) -> TeamResponse:
    return team.update_member(session, actor, membership_id, body)

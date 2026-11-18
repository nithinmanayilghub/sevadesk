# HTTP routes for log-in, log-out, "who am I" (story 2.2, FR-8, AD-5), and invite accept
# (story 2.5, FR-9): accepting an invite also logs the person in.
from fastapi import APIRouter, Request, Response
from sqlalchemy.orm import Session

from app.core.client_ip import client_ip
from app.core.db import SessionDep
from app.core.errors import ErrorEnvelope
from app.core.session_cookie import SessionTokenCookie, clear_session_cookie, set_session_cookie
from app.modules.accounts import service
from app.modules.accounts.dependencies import ActorDep
from app.modules.accounts.schemas import (
    AcceptInviteRequest,
    Actor,
    InvitePreview,
    InviteTokenRequest,
    LoginRequest,
    MeResponse,
    ThemeUpdate,
)

router = APIRouter(prefix="/api/v1")

# Listed so the OpenAPI schema (and so the frontend types) know the error shape.
_ERROR = {"model": ErrorEnvelope}


@router.post(
    "/login",
    operation_id="log_in",
    responses={401: _ERROR, 422: _ERROR, 429: _ERROR, 503: _ERROR},
)
def log_in(
    body: LoginRequest, request: Request, response: Response, session: SessionDep, old_token: SessionTokenCookie = None
) -> MeResponse:
    # A shared phone: end the previous person's session first (D11).
    service.end_session(session, old_token)
    token, actor = service.log_in(session, body.email, body.password, client_ip(request))
    set_session_cookie(response, token)
    return _me(session, actor)


@router.post("/logout", status_code=204, operation_id="log_out")
def log_out(response: Response, session: SessionDep, token: SessionTokenCookie = None) -> None:
    # No ActorDep: an expired or unknown session can still log out without an error.
    service.end_session(session, token)
    clear_session_cookie(response)


@router.post("/invites/preview", operation_id="preview_invite", responses={404: _ERROR, 422: _ERROR})
def preview_invite(body: InviteTokenRequest, session: SessionDep) -> InvitePreview:
    # POST, not GET /invites/{token}: request logs record the path, and the token is a secret.
    return service.preview_invite(session, body.token)


@router.post(
    "/invites/accept",
    operation_id="accept_invite",
    responses={404: _ERROR, 409: _ERROR, 422: _ERROR},
)
def accept_invite(
    body: AcceptInviteRequest, response: Response, session: SessionDep, old_token: SessionTokenCookie = None
) -> MeResponse:
    # A shared phone: end the previous person's session first (D11).
    service.end_session(session, old_token)
    token, actor = service.accept_invite(session, body.token, body.password)
    set_session_cookie(response, token)
    return _me(session, actor)


@router.get("/me", operation_id="get_me", responses={401: _ERROR})
def get_me(session: SessionDep, actor: ActorDep) -> MeResponse:
    return _me(session, actor)


def _me(session: Session, actor: Actor) -> MeResponse:
    # One place builds the "who am I" answer, for both log-in and /me.
    return MeResponse(
        roles=sorted(actor.roles),
        permissions=service.permissions_for(actor.roles),
        theme=service.get_theme(session, actor.user_id),
    )


@router.put("/me/theme", status_code=204, operation_id="set_theme", responses={401: _ERROR, 422: _ERROR})
def set_theme(body: ThemeUpdate, session: SessionDep, actor: ActorDep) -> None:
    # Saves the look for this User, so it follows them to every device.
    service.set_theme(session, actor.user_id, body.theme)

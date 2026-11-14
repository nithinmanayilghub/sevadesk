# HTTP routes for log-in, log-out and "who am I" (story 2.2, FR-8, AD-5).
from fastapi import APIRouter, Request, Response

from app.core.client_ip import client_ip
from app.core.db import SessionDep
from app.core.errors import ErrorEnvelope
from app.core.session_cookie import SessionTokenCookie, clear_session_cookie, set_session_cookie
from app.modules.accounts import service
from app.modules.accounts.dependencies import ActorDep
from app.modules.accounts.schemas import LoginRequest, MeResponse

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
    return MeResponse(roles=sorted(actor.roles))


@router.post("/logout", status_code=204, operation_id="log_out")
def log_out(response: Response, session: SessionDep, token: SessionTokenCookie = None) -> None:
    # No ActorDep: an expired or unknown session can still log out without an error.
    service.end_session(session, token)
    clear_session_cookie(response)


@router.get("/me", operation_id="get_me", responses={401: _ERROR})
def get_me(actor: ActorDep) -> MeResponse:
    return MeResponse(roles=sorted(actor.roles))

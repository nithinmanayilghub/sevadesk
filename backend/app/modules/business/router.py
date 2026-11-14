# HTTP route for sign-up: POST /api/v1/signup. Sign-up also logs the new Owner in.
from fastapi import APIRouter, Response

from app.core.db import SessionDep
from app.core.errors import ErrorEnvelope
from app.core.session_cookie import SessionTokenCookie, set_session_cookie
from app.modules.accounts import service as accounts_service
from app.modules.business import service
from app.modules.business.schemas import SignupRequest, SignupResponse

router = APIRouter(prefix="/api/v1")


@router.post(
    "/signup",
    status_code=201,
    operation_id="sign_up",
    responses={409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def sign_up(
    body: SignupRequest, response: Response, session: SessionDep, old_token: SessionTokenCookie = None
) -> SignupResponse:
    # A shared phone: end the previous person's session first (D11).
    accounts_service.end_session(session, old_token)
    result, token = service.sign_up(session, body)
    set_session_cookie(response, token)
    return result

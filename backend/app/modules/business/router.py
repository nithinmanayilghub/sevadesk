# HTTP route for sign-up: POST /api/v1/signup.
from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.errors import ErrorEnvelope
from app.modules.business import service
from app.modules.business.schemas import SignupRequest, SignupResponse

router = APIRouter(prefix="/api/v1")


@router.post(
    "/signup",
    status_code=201,
    operation_id="sign_up",
    responses={409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
def sign_up(body: SignupRequest, session: SessionDep) -> SignupResponse:
    return service.sign_up(session, body)

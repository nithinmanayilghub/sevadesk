# HTTP routes of the business module.
# - POST /api/v1/signup: sign-up also logs the new Owner in.
# - /api/v1/services: Settings → Services, Owner only (story 3.1). The Role check lives in service.py.
import uuid

from fastapi import APIRouter, Response

from app.core.db import SessionDep
from app.core.errors import ErrorEnvelope
from app.core.session_cookie import SessionTokenCookie, set_session_cookie
from app.modules.accounts import service as accounts_service
from app.modules.accounts.dependencies import ActorDep
from app.modules.business import service
from app.modules.business.schemas import ServiceIn, ServiceList, ServiceOut, SignupRequest, SignupResponse

router = APIRouter(prefix="/api/v1")

# Listed so the OpenAPI schema (and so the frontend types) know the error shape.
_ERROR = {"model": ErrorEnvelope}


@router.post(
    "/signup",
    status_code=201,
    operation_id="sign_up",
    responses={409: _ERROR, 422: _ERROR},
)
def sign_up(
    body: SignupRequest, response: Response, session: SessionDep, old_token: SessionTokenCookie = None
) -> SignupResponse:
    # A shared phone: end the previous person's session first (D11).
    accounts_service.end_session(session, old_token)
    result, token = service.sign_up(session, body)
    set_session_cookie(response, token)
    return result


@router.get("/services", operation_id="list_services", responses={401: _ERROR, 403: _ERROR})
def list_services(session: SessionDep, actor: ActorDep) -> ServiceList:
    return service.list_services(session, actor)


@router.post(
    "/services",
    status_code=201,
    operation_id="create_service",
    responses={401: _ERROR, 403: _ERROR, 422: _ERROR},
)
def create_service(body: ServiceIn, session: SessionDep, actor: ActorDep) -> ServiceOut:
    return service.create_service(session, actor, body)


@router.put(
    "/services/{service_id}",
    operation_id="replace_service",
    responses={401: _ERROR, 403: _ERROR, 404: _ERROR, 422: _ERROR},
)
def replace_service(service_id: uuid.UUID, body: ServiceIn, session: SessionDep, actor: ActorDep) -> ServiceOut:
    return service.replace_service(session, actor, service_id, body)

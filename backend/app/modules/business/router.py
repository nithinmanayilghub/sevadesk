# HTTP routes of the business module.
# - POST /api/v1/signup: sign-up also logs the new Owner in.
# - /api/v1/services: Settings → Services, Owner only (story 3.1). The Role check lives in service.py.
# - /api/v1/setup and /api/v1/chat/{chat_slug}: the chat link and the public Chat Page (story 3.3).
import uuid

from fastapi import APIRouter, Response

from app.core.db import SessionDep
from app.core.errors import ErrorEnvelope
from app.core.session_cookie import SessionTokenCookie, set_session_cookie
from app.modules.accounts import service as accounts_service
from app.modules.accounts.dependencies import ActorDep
from app.modules.business import service
from app.modules.business.schemas import (
    ChatPageOut,
    ClosedDayIn,
    ClosedDayList,
    ClosedDayOut,
    ServiceIn,
    ServiceList,
    ServiceOut,
    SetupOut,
    SignupRequest,
    SignupResponse,
    WeekIn,
    WorkingHoursOut,
)

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


# Settings → Working Hours, Owner only (story 3.2). The Role check lives in service.py.
@router.get("/working-hours", operation_id="get_working_hours", responses={401: _ERROR, 403: _ERROR})
def get_working_hours(session: SessionDep, actor: ActorDep) -> WorkingHoursOut:
    return service.get_working_hours(session, actor)


@router.put(
    "/working-hours",
    operation_id="replace_working_hours",
    responses={401: _ERROR, 403: _ERROR, 422: _ERROR},
)
def replace_working_hours(body: WeekIn, session: SessionDep, actor: ActorDep) -> WorkingHoursOut:
    return service.replace_working_hours(session, actor, body)


@router.get("/closed-days", operation_id="list_closed_days", responses={401: _ERROR, 403: _ERROR})
def list_closed_days(session: SessionDep, actor: ActorDep) -> ClosedDayList:
    return service.list_closed_days(session, actor)


@router.post(
    "/closed-days",
    status_code=201,
    operation_id="add_closed_day",
    responses={401: _ERROR, 403: _ERROR, 422: _ERROR},
)
def add_closed_day(body: ClosedDayIn, session: SessionDep, actor: ActorDep) -> ClosedDayOut:
    return service.add_closed_day(session, actor, body)


@router.delete(
    "/closed-days/{closed_day_id}",
    status_code=204,
    operation_id="remove_closed_day",
    # 422: a closed_day_id that is not a UUID. Listed so the frontend types know our error shape.
    responses={401: _ERROR, 403: _ERROR, 404: _ERROR, 422: _ERROR},
)
def remove_closed_day(closed_day_id: uuid.UUID, session: SessionDep, actor: ActorDep) -> None:
    service.remove_closed_day(session, actor, closed_day_id)


# The Owner's chat link and setup status, for Settings and the Dashboard checklist (story 3.3).
@router.get("/setup", operation_id="get_setup", responses={401: _ERROR, 403: _ERROR})
def get_setup(session: SessionDep, actor: ActorDep) -> SetupOut:
    return service.get_setup(session, actor)


# The public Chat Page. No ActorDep on purpose: Customers have no login, and the tenant
# comes from the slug only (AD-3 b), never from a session cookie.
@router.get("/chat/{chat_slug}", operation_id="get_chat_page", responses={404: _ERROR})
def get_chat_page(chat_slug: str, session: SessionDep) -> ChatPageOut:
    return service.get_chat_page(session, chat_slug)

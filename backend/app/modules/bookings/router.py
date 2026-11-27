# HTTP routes of the bookings module.
# - GET /api/v1/bookings/slots: the free Slots of one Service (story 5.1, FR-17).
#   Owner and Staff only; the Role check lives in service.py.
import uuid

from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.errors import ErrorEnvelope
from app.modules.accounts.dependencies import ActorDep
from app.modules.bookings import service
from app.modules.bookings.schemas import FreeSlotsOut

router = APIRouter(prefix="/api/v1/bookings")

# Listed so the OpenAPI schema (and so the frontend types) know the error shape.
_ERROR = {"model": ErrorEnvelope}


@router.get(
    "/slots",
    operation_id="list_free_slots",
    responses={401: _ERROR, 403: _ERROR, 404: _ERROR, 422: _ERROR},
)
def list_free_slots(service_id: uuid.UUID, session: SessionDep, actor: ActorDep) -> FreeSlotsOut:
    return service.list_free_slots(session, actor, service_id)

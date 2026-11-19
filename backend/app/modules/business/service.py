# The business front door (AD-2). Other modules call only these functions.
# - sign_up: the whole sign-up flow (FR-7).
# - Services (story 3.1, FR-12): the Owner's list / add / replace, and list_active_services
#   for the Chat Page and the Agent (later stories).
import uuid

from sqlalchemy.orm import Session

from app.core.tenancy import tenant_scope

# Import the module, not the function, so every call goes through accounts_service.<name>.
from app.modules.accounts import service as accounts_service
from app.modules.accounts.schemas import Actor, Permission
from app.modules.business.models import Service
from app.modules.business.repository import BusinessRepository, ServiceRepository
from app.modules.business.schemas import ServiceIn, ServiceList, ServiceOut, SignupRequest, SignupResponse


def sign_up(session: Session, request: SignupRequest) -> tuple[SignupResponse, str]:
    """Create the Business and its Owner, and log the Owner in. Returns (response, session token)."""
    # One transaction (owned by the request, AD-15): if any step fails, nothing is saved.
    business = BusinessRepository(session).add(request.business_name)
    # The tenant is server-derived: this transaction just created it.
    with tenant_scope(business.id):
        owner = accounts_service.create_owner(session, request.email, request.password)
    # A new Owner is logged in at once (story 2.2).
    token = accounts_service.start_session(session, owner.user_id)
    return SignupResponse(business_id=business.id, business_name=business.name), token


def _out(row: Service) -> ServiceOut:
    return ServiceOut(
        service_id=row.id,
        name=row.name,
        duration_minutes=row.duration_minutes,
        price_paise=row.price_paise,
        is_active=row.is_active,
    )


def list_services(session: Session, actor: Actor) -> ServiceList:
    """Every Service of the Owner's Business, active or not, oldest first."""
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    return ServiceList(services=[_out(row) for row in ServiceRepository(session).list_all()])


def create_service(session: Session, actor: Actor, data: ServiceIn) -> ServiceOut:
    """Add a Service. No commit here: the request owns the transaction (AD-15)."""
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    row = ServiceRepository(session).add(
        Service(
            name=data.name,
            duration_minutes=data.duration_minutes,
            price_paise=data.price_paise,
            is_active=data.is_active,
        )
    )
    return _out(row)


def replace_service(session: Session, actor: Actor, service_id: uuid.UUID, data: ServiceIn) -> ServiceOut:
    """Replace every field of one Service. Deactivate = is_active False. Never deletes (FR-12)."""
    # Role check FIRST: a 403 then says nothing about whether this id exists (story 2.4).
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    # The tenant filter hides other Businesses' Services: their ids answer 404 (FR-11).
    row = ServiceRepository(session).get_or_raise(service_id)
    row.name = data.name
    row.duration_minutes = data.duration_minutes
    row.price_paise = data.price_paise
    row.is_active = data.is_active
    session.flush()  # send the UPDATE now, so a database error shows here, inside the request
    return _out(row)


def list_active_services(session: Session) -> list[ServiceOut]:
    """What the Business really offers now (FR-12). For the Chat Page and the Agent.

    No Role check: Customers see these too. The caller must already be in a tenant scope.
    """
    return [_out(row) for row in ServiceRepository(session).list_active()]

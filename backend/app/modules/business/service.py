# The business front door. sign_up runs the whole sign-up flow (FR-7).
from sqlalchemy.orm import Session

from app.core.tenancy import tenant_scope

# Import the module, not the function, so every call goes through accounts_service.<name>.
from app.modules.accounts import service as accounts_service
from app.modules.business.repository import BusinessRepository
from app.modules.business.schemas import SignupRequest, SignupResponse


def sign_up(session: Session, request: SignupRequest) -> SignupResponse:
    # One transaction (owned by the request, AD-15): if any step fails, nothing is saved.
    business = BusinessRepository(session).add(request.business_name)
    # The tenant is server-derived: this transaction just created it.
    with tenant_scope(business.id):
        accounts_service.create_owner(session, request.email, request.password)
    return SignupResponse(business_id=business.id, business_name=business.name)

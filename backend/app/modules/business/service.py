# The business front door. sign_up runs the whole sign-up flow (FR-7).
from sqlalchemy.orm import Session

from app.core.tenancy import tenant_scope

# Import the module, not the function, so every call goes through accounts_service.<name>.
from app.modules.accounts import service as accounts_service
from app.modules.business.repository import BusinessRepository
from app.modules.business.schemas import SignupRequest, SignupResponse


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

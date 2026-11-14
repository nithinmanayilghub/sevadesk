# A tiny test-only app (story 2.3, D3). No production endpoint reads tenant rows by id yet,
# so these "probe" routes use the real building blocks (ActorDep, SessionDep, the error
# handlers) the way future endpoints will. They are never part of the real app.
from fastapi import FastAPI

from app.core.errors import register_error_handlers
from app.core.tenancy import current_business_id
from app.modules.accounts.dependencies import ActorDep


def build_probe_app() -> FastAPI:
    probe = FastAPI()
    register_error_handlers(probe)

    @probe.get("/probe/business")
    def which_business(actor: ActorDep) -> dict[str, str]:
        # Reads the tenant context, as every tenant repository does.
        return {"business_id": str(current_business_id())}

    @probe.get("/probe/no-actor")
    def no_actor() -> dict[str, str]:
        # No ActorDep: a cookie alone must not set a Business, so this raises.
        return {"business_id": str(current_business_id())}

    return probe

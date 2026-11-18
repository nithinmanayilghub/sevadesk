# A tiny test-only app (story 2.3, D3), written before any production endpoint read tenant
# rows by id. These "probe" routes use the real building blocks (ActorDep, SessionDep, the
# error handlers) in small, fixed ways the tests rely on. They are never part of the real app.
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.db import SessionDep
from app.core.errors import register_error_handlers
from app.core.tenancy import current_business_id
from app.modules.accounts import service as accounts_service
from app.modules.accounts.dependencies import ActorDep
from app.modules.accounts.repository import MembershipRepository
from app.modules.accounts.schemas import Permission


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

    @probe.get("/probe/memberships/{membership_id}")
    def read_membership(membership_id: uuid.UUID, session: SessionDep, actor: ActorDep) -> dict[str, str]:
        # A read by id, as a future "show one record" endpoint will do it.
        row = MembershipRepository(session).get_or_raise(membership_id)
        return {"id": str(row.id)}

    @probe.post("/probe/memberships/{membership_id}/deactivate", status_code=204)
    def deactivate_membership(membership_id: uuid.UUID, session: SessionDep, actor: ActorDep) -> None:
        # A write by id: find the row first, then change it. SessionDep saves it at the end.
        row = MembershipRepository(session).get_or_raise(membership_id)
        row.is_active = False

    # --- Role checks (story 2.4, FR-10) ---

    @probe.get("/probe/permissions/{permission}")
    def check_permission(permission: Permission, actor: ActorDep) -> dict[str, str]:
        # The one Role check, as every future service will call it.
        accounts_service.require_roles(actor, permission)
        return {"ok": "yes"}

    @probe.post("/probe/team/{membership_id}/deactivate", status_code=204)
    def deactivate_team_member(membership_id: uuid.UUID, session: SessionDep, actor: ActorDep) -> None:
        # The right order: check the Role FIRST, then look up the row. So a 403 says
        # nothing about whether the row exists.
        accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
        row = MembershipRepository(session).get_or_raise(membership_id)
        row.is_active = False

    @probe.post("/probe/team/{membership_id}/deactivate-late", status_code=204)
    def deactivate_team_member_late(membership_id: uuid.UUID, session: SessionDep, actor: ActorDep) -> None:
        # The WRONG order on purpose: write first, check after. It proves the safety net,
        # not the order: the 403 rolls back the request's transaction, so nothing is saved.
        row = MembershipRepository(session).get_or_raise(membership_id)
        row.is_active = False
        session.flush()  # send the UPDATE to the database now, so a rollback has real work to undo
        accounts_service.require_roles(actor, Permission.MANAGE_SETUP)

    return probe


def probe_client(owner: TestClient, **kwargs) -> TestClient:
    """A client for the probe app that carries the Owner's session cookie."""
    return TestClient(
        build_probe_app(),
        base_url="https://testserver",
        headers={"Origin": "https://testserver"},
        cookies=owner.cookies,
        **kwargs,
    )

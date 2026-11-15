# The HTTP front door of accounts (AD-2 note, story 2.2): FastAPI dependencies that other
# modules' routers may use. Like service.py, other modules may import this file.
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends

from app.core.db import SessionDep
from app.core.session_cookie import SessionTokenCookie
from app.core.tenancy import tenant_scope
from app.modules.accounts import service
from app.modules.accounts.schemas import Actor


def get_actor(session: SessionDep, token: SessionTokenCookie = None) -> Actor:
    """Who is calling: the session cookie turned into an Actor, or a 401 (AD-5)."""
    return service.resolve_session(session, token)


async def actor_in_tenant_scope(actor: Annotated[Actor, Depends(get_actor)]) -> AsyncIterator[Actor]:
    """The route runs inside the Actor's own Business (AD-3), so tenant repositories just work."""
    # Why async: FastAPI runs a sync dependency in a worker thread, and a ContextVar set
    # there never reaches the route. An async one runs in the request's own task, and
    # that context is copied into the route's thread.
    with tenant_scope(actor.business_id):
        yield actor


# Put `actor: ActorDep` in a route, and the route runs only for logged-in Users,
# inside their own Business. scope="function" ends the tenant scope when the route
# returns, before any BackgroundTasks run (jobs get their Business from the payload, AD-3).
ActorDep = Annotated[Actor, Depends(actor_in_tenant_scope, scope="function")]

# The HTTP front door of accounts (AD-2 note, story 2.2): FastAPI dependencies that other
# modules' routers may use. Like service.py, other modules may import this file.
from typing import Annotated

from fastapi import Depends

from app.core.db import SessionDep
from app.core.session_cookie import SessionTokenCookie
from app.modules.accounts import service
from app.modules.accounts.schemas import Actor


def get_actor(session: SessionDep, token: SessionTokenCookie = None) -> Actor:
    """Who is calling: the session cookie turned into an Actor, or a 401 (AD-5)."""
    return service.resolve_session(session, token)


# Put `actor: ActorDep` in a route, and the route runs only for logged-in Users.
ActorDep = Annotated[Actor, Depends(get_actor)]

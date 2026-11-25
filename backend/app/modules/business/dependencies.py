# The HTTP front door of business for public chat routes (story 4.1). Like service.py,
# other modules' routers may import this file (inbox does, for its chat Message routes).
#
# Every public chat route has {chat_slug} in its path. One of these two steps turns the slug
# into a Business and runs the code inside that Business's tenant scope (AD-3 source b):
# - ChatBusinessDep: for a route that always needs the Business (the normal case).
# - chat_business_scope(): for the one route that must first try Redis only, and reads the
#   database only when it has to (the Chat Page poll, story 4.2: a FastAPI dependency would
#   query Postgres before the route even starts).
# Both use service.find_chat_business, so no public route finds the Business in its own way.
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import SessionDep
from app.core.tenancy import tenant_scope
from app.modules.business import service
from app.modules.business.schemas import ChatBusiness


def get_chat_business(chat_slug: str, session: SessionDep) -> ChatBusiness:
    """The Business this slug names, or a 404 (FastAPI reads chat_slug from the path)."""
    return service.find_chat_business(session, chat_slug)


async def chat_business_in_tenant_scope(
    business: Annotated[ChatBusiness, Depends(get_chat_business)],
) -> AsyncIterator[ChatBusiness]:
    # Why async: FastAPI runs a sync dependency in a worker thread, and a ContextVar set
    # there never reaches the route. An async one runs in the request's own task, and that
    # context is copied into the route's thread. (The same reason as accounts/dependencies.py.)
    with tenant_scope(business.business_id):
        yield business


@contextmanager
def chat_business_scope(session: Session, chat_slug: str) -> Iterator[ChatBusiness]:
    """`with chat_business_scope(session, slug) as business:` — the code inside runs in the
    slug's Business. A bad or unknown slug raises NotFound (404) before anything runs."""
    business = service.find_chat_business(session, chat_slug)
    with tenant_scope(business.business_id):
        yield business


# Put `business: ChatBusinessDep` in a public chat route: it runs inside the slug's Business.
# scope="function" ends the tenant scope when the route returns.
ChatBusinessDep = Annotated[ChatBusiness, Depends(chat_business_in_tenant_scope, scope="function")]

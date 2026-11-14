# Tenant context (AD-3): which Business the current code is working for.
#
# A ContextVar is a variable that has its own value per request (and per asyncio task),
# so two requests running at the same time never see each other's Business.
#
# Two scopes:
# - tenant_scope(business_id): "we now work for this Business". Repositories read it.
# - system_scope(caller): a rare, audited exception for global lookups, such as
#   "does this email already exist?" during sign-up. Only allow-listed callers may use it.
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Callers allowed to enter system scope. Each new one must be added here on purpose.
SYSTEM_SCOPE_CALLERS: frozenset[str] = frozenset({"signup", "login"})

_business_id: ContextVar[uuid.UUID | None] = ContextVar("business_id", default=None)
_in_system_scope: ContextVar[bool] = ContextVar("in_system_scope", default=False)


class TenantContextMissing(RuntimeError):
    """Tenant data was used, but no Business was set for this code."""


class SystemScopeRequired(RuntimeError):
    """A global lookup was tried outside system_scope."""


def current_business_id() -> uuid.UUID:
    business_id = _business_id.get()
    if business_id is None:
        raise TenantContextMissing("No Business is set. Use tenant_scope().")
    return business_id


@contextmanager
def tenant_scope(business_id: uuid.UUID) -> Iterator[None]:
    # The token remembers the old value, so leaving the scope restores it.
    token = _business_id.set(business_id)
    try:
        yield
    finally:
        _business_id.reset(token)


@contextmanager
def system_scope(caller: str) -> Iterator[None]:
    if caller not in SYSTEM_SCOPE_CALLERS:
        raise ValueError(f"{caller!r} may not use system_scope")
    # Audit line: who used the exception. No email or other personal data here.
    logger.info("system_scope entered", extra={"caller": caller})
    token = _in_system_scope.set(True)
    try:
        yield
    finally:
        _in_system_scope.reset(token)


@contextmanager
def session_lookup() -> Iterator[None]:
    """AD-3 source (a): staff session -> membership. Only accounts.service.resolve_session uses it.

    It allows the same global lookups as system_scope, but writes no audit line:
    it runs on every logged-in request, so a line each time would bury the rare real ones.
    """
    token = _in_system_scope.set(True)
    try:
        yield
    finally:
        _in_system_scope.reset(token)


def require_system_scope() -> None:
    if not _in_system_scope.get():
        raise SystemScopeRequired("This lookup is allowed only inside system_scope().")

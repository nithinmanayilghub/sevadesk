# Unit tests for tenant context (AD-3): which Business the current code works for.
import logging
import uuid

import pytest

from app.core.tenancy import (
    SystemScopeRequired,
    TenantContextMissing,
    current_business_id,
    require_system_scope,
    session_lookup,
    system_scope,
    tenant_scope,
)

BUSINESS_A = uuid.uuid7()
BUSINESS_B = uuid.uuid7()


def test_current_business_id_raises_outside_scope():
    # Behaviour: code that forgets to set a tenant fails loudly, never "sees all".
    with pytest.raises(TenantContextMissing):
        current_business_id()


def test_tenant_scope_sets_and_restores():
    # Behaviour: a scope sets the Business; leaving it brings back the old value.
    with tenant_scope(BUSINESS_A):
        assert current_business_id() == BUSINESS_A
        with tenant_scope(BUSINESS_B):
            assert current_business_id() == BUSINESS_B
        assert current_business_id() == BUSINESS_A
    with pytest.raises(TenantContextMissing):
        current_business_id()


def test_system_scope_refuses_unknown_caller():
    # Behaviour: only callers on the allow-list may enter system scope.
    with pytest.raises(ValueError), system_scope("hacker"):
        pass


def test_require_system_scope_only_inside():
    # Behaviour: global lookups (like "does this email exist?") work only in system scope.
    with pytest.raises(SystemScopeRequired):
        require_system_scope()
    with system_scope("signup"):
        require_system_scope()
    with pytest.raises(SystemScopeRequired):
        require_system_scope()


def test_login_is_an_allowed_caller_but_session_is_not():
    # Behaviour: log-in may do the email lookup; the session lookup has its own quiet guard.
    with system_scope("login"):
        require_system_scope()
    with pytest.raises(ValueError), system_scope("session"):
        pass


def test_session_lookup_allows_global_lookup_without_a_log_line(caplog):
    # Behaviour: session -> membership (AD-3 source (a)) runs on every request, so it is quiet.
    with caplog.at_level(logging.DEBUG, logger="app.core.tenancy"), session_lookup():
        require_system_scope()
    assert caplog.records == []
    with pytest.raises(SystemScopeRequired):
        require_system_scope()


def test_system_scope_writes_audit_log(caplog):
    # Behaviour: every entry into system scope leaves an audit line naming the caller.
    with caplog.at_level(logging.INFO, logger="app.core.tenancy"), system_scope("signup"):
        pass
    assert any(getattr(r, "caller", None) == "signup" for r in caplog.records)

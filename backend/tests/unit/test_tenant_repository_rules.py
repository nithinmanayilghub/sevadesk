# Code guard (story 2.3, AD-3): no tenant repository method takes business_id.
# The Business always comes from tenant_scope, never from the caller, so a caller
# cannot ask for another Business's rows.
import importlib
import inspect
import pkgutil

import pytest

import app.modules
from app.core.repository import TenantRepository
from app.modules.accounts.repository import MembershipRepository

pytestmark = pytest.mark.isolation


def all_subclasses(cls: type) -> set[type]:
    """Children, grandchildren, and so on."""
    found = set()
    for child in cls.__subclasses__():
        found |= {child} | all_subclasses(child)
    return found


def test_no_tenant_repository_method_takes_business_id():
    # Import every module file, so every repository class exists. (Not app.main: it starts telemetry.)
    for info in pkgutil.walk_packages(app.modules.__path__, "app.modules."):
        importlib.import_module(info.name)
    repositories = all_subclasses(TenantRepository)
    assert MembershipRepository in repositories  # the scan cannot pass by finding nothing
    for repository in repositories:
        for name, method in inspect.getmembers(repository, inspect.isfunction):
            assert "business_id" not in inspect.signature(method).parameters, f"{repository.__name__}.{name}"

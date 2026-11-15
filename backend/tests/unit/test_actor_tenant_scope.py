# Unit test: the ActorDep wrapper sets the tenant scope and clears it again (story 2.3, D1).
# We drive the async generator by hand, the way FastAPI does: enter, use, then close.
import asyncio
import uuid

import pytest

from app.core.tenancy import TenantContextMissing, current_business_id
from app.modules.accounts.dependencies import actor_in_tenant_scope
from app.modules.accounts.schemas import Actor, Role

pytestmark = pytest.mark.isolation


def test_scope_is_set_inside_and_cleared_after():
    # Behaviour: the Business is set while the route runs, and gone when the dependency exits.
    actor = Actor(user_id=uuid.uuid7(), membership_id=uuid.uuid7(), business_id=uuid.uuid7(), roles={Role.OWNER})

    async def drive() -> None:
        dependency = actor_in_tenant_scope(actor)
        assert await anext(dependency) is actor
        assert current_business_id() == actor.business_id
        await dependency.aclose()
        with pytest.raises(TenantContextMissing):
            current_business_id()

    asyncio.run(drive())

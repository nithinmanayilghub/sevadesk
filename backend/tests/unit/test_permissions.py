# Unit tests: the FR-10 permission table and the one require_roles helper (story 2.4, AR-7).
import itertools
import uuid

import pytest

from app.core.errors import Forbidden
from app.modules.accounts.permissions import (
    ALLOWED_ROLES,
    assigned_bookings_filter,
    permissions_for,
    require_roles,
)
from app.modules.accounts.schemas import Actor, Permission, Role

# FR-10, copied by hand from the PRD table. If the table in the code drifts, this test fails.
EXPECTED = {
    Permission.MANAGE_SETUP: {Role.OWNER},
    Permission.USE_INBOX_AND_BOOKINGS: {Role.OWNER, Role.STAFF},
    Permission.SEE_OWN_BOOKINGS: {Role.OWNER, Role.STAFF, Role.TECHNICIAN},
    Permission.SEE_DASHBOARD: {Role.OWNER, Role.STAFF},
}

# Every non-empty mix of Roles a person can have: 7 of them (3 single, 3 pairs, 1 with all three).
ALL_ROLE_SETS = [set(combo) for size in (1, 2, 3) for combo in itertools.combinations(Role, size)]


def make_actor(roles: set[Role]) -> Actor:
    return Actor(user_id=uuid.uuid7(), membership_id=uuid.uuid7(), business_id=uuid.uuid7(), roles=roles)


def test_table_matches_fr10():
    # Behaviour: the table in the code is exactly the PRD's FR-10 table.
    assert {permission: set(roles) for permission, roles in ALLOWED_ROLES.items()} == EXPECTED


@pytest.mark.parametrize("permission", list(Permission))
@pytest.mark.parametrize("roles", ALL_ROLE_SETS, ids=lambda roles: "+".join(sorted(roles)))
def test_require_roles_allows_or_forbids(permission, roles):
    # Behaviour: any one allowed Role is enough (a union); with none, the call is Forbidden.
    actor = make_actor(roles)
    if roles & EXPECTED[permission]:
        require_roles(actor, permission)  # no error
    else:
        with pytest.raises(Forbidden):
            require_roles(actor, permission)


@pytest.mark.parametrize("permission", list(Permission))
def test_empty_roles_get_nothing(permission):
    # Behaviour: an Actor with no Roles may do nothing at all.
    with pytest.raises(Forbidden):
        require_roles(make_actor(set()), permission)
    assert permissions_for(set()) == []


def test_staff_cannot_manage_setup_but_can_see_dashboard():
    # Behaviour: Staff may see the Dashboard, but only the Owner may manage setup.
    staff = make_actor({Role.STAFF})
    with pytest.raises(Forbidden):
        require_roles(staff, Permission.MANAGE_SETUP)
    require_roles(staff, Permission.SEE_DASHBOARD)


def test_permissions_for_technician_only():
    # Behaviour: a Technician-only User may only see their own Bookings.
    assert permissions_for({Role.TECHNICIAN}) == [Permission.SEE_OWN_BOOKINGS]


def test_permissions_for_staff_and_technician_is_union():
    # Behaviour: two Roles give the rights of both, in the table's order.
    assert permissions_for({Role.STAFF, Role.TECHNICIAN}) == [
        Permission.USE_INBOX_AND_BOOKINGS,
        Permission.SEE_OWN_BOOKINGS,
        Permission.SEE_DASHBOARD,
    ]


def test_technician_only_sees_own_bookings():
    # Behaviour: the bookings filter for a Technician-only Actor is their own membership id.
    actor = make_actor({Role.TECHNICIAN})
    assert assigned_bookings_filter(actor) == actor.membership_id


@pytest.mark.parametrize(
    "roles",
    [{Role.OWNER, Role.TECHNICIAN}, {Role.STAFF}, {Role.STAFF, Role.TECHNICIAN}],
    ids=["owner+technician", "staff", "staff+technician"],
)
def test_owner_or_staff_sees_all_bookings(roles):
    # Behaviour: Owner and Staff approve Bookings, so they get no filter (they see all).
    assert assigned_bookings_filter(make_actor(roles)) is None


def test_forbidden_error_shape():
    # Behaviour: Forbidden is a 403 with a fixed code and message.
    error = Forbidden()
    assert (error.status_code, error.code, error.message) == (403, "forbidden", "You don't have access to this.")

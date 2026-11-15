# Integration tests: Role checks over real HTTP (story 2.4, FR-10). A forbidden call gets 403
# and changes nothing. The routes live in the test-only probe app (probe_app.py), because no
# real endpoint needs a Role yet. The unit tests (test_permissions.py) cover every FR-10 row;
# these prove the same helper works end to end: cookie -> Actor -> require_roles -> 403.
import uuid

import pytest
from tests.integration.conftest import assert_not_found, membership_is_active, membership_of, set_owner_roles
from tests.integration.probe_app import probe_client

FORBIDDEN_BODY = {"error": {"code": "forbidden", "message": "You don't have access to this."}}


def as_roles(sign_up_owner, roles: list[str]):
    """Sign up a Business, then give its one member these Roles. Returns (probe client, business_id)."""
    owner, business_id = sign_up_owner()
    set_owner_roles(business_id, roles)
    return probe_client(owner), business_id


def test_allowed_role_gets_200(sign_up_owner):
    # Behaviour: Staff may use the Inbox and approve Bookings.
    staff, _ = as_roles(sign_up_owner, ["staff"])
    response = staff.get("/probe/permissions/use_inbox_and_bookings")
    assert response.status_code == 200
    assert response.json() == {"ok": "yes"}


def test_forbidden_role_gets_403_envelope(sign_up_owner):
    # Behaviour: a Technician may not manage setup; the answer is our 403 error envelope.
    technician, _ = as_roles(sign_up_owner, ["technician"])
    response = technician.get("/probe/permissions/manage_setup")
    assert response.status_code == 403
    assert response.json() == FORBIDDEN_BODY


def test_multi_role_gets_union(sign_up_owner):
    # Behaviour: Staff + Technician get the rights of both Roles, and no more.
    both, _ = as_roles(sign_up_owner, ["staff", "technician"])
    assert both.get("/probe/permissions/see_dashboard").status_code == 200
    assert both.get("/probe/permissions/manage_setup").status_code == 403


def test_forbidden_write_changes_nothing(sign_up_owner):
    # Behaviour: the Role check runs first, so a forbidden write never starts.
    technician, business_id = as_roles(sign_up_owner, ["technician"])
    response = technician.post(f"/probe/team/{membership_of(business_id)}/deactivate")
    assert response.status_code == 403
    assert membership_is_active(business_id)


def test_late_check_still_changes_nothing(sign_up_owner):
    # Behaviour: even if a service writes BEFORE it checks, the 403 rolls the write back.
    technician, business_id = as_roles(sign_up_owner, ["technician"])
    response = technician.post(f"/probe/team/{membership_of(business_id)}/deactivate-late")
    assert response.status_code == 403
    assert membership_is_active(business_id)


def test_403_does_not_reveal_records(sign_up_owner):
    # Behaviour: own id, another Business's id, or a missing id: the same 403, so nothing leaks.
    technician, business_id = as_roles(sign_up_owner, ["technician"])
    _, other_business_id = sign_up_owner()
    ids = [membership_of(business_id), membership_of(other_business_id), uuid.uuid7()]
    for membership_id in ids:
        response = technician.post(f"/probe/team/{membership_id}/deactivate")
        assert (response.status_code, response.json()) == (403, FORBIDDEN_BODY)
    assert membership_is_active(other_business_id)


def test_owner_write_is_allowed(sign_up_owner):
    # Behaviour: the Owner may manage the team, so the write happens.
    owner, business_id = sign_up_owner()
    response = probe_client(owner).post(f"/probe/team/{membership_of(business_id)}/deactivate")
    assert response.status_code == 204
    assert not membership_is_active(business_id)


def test_new_roles_apply_on_next_request(sign_up_owner):
    # Behaviour: Roles are read on every request, so a change works at once, with the same cookie.
    owner, business_id = sign_up_owner()
    client = probe_client(owner)
    assert client.get("/probe/permissions/manage_setup").status_code == 200
    set_owner_roles(business_id, ["staff"])
    assert client.get("/probe/permissions/manage_setup").status_code == 403


def test_me_lists_only_own_permissions(sign_up_owner):
    # Behaviour: /me tells the app what THIS User may do, so it can hide the rest (UX-DR27).
    owner, business_id = sign_up_owner()
    set_owner_roles(business_id, ["technician"])
    response = owner.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json() == {"roles": ["technician"], "permissions": ["see_own_bookings"]}


@pytest.mark.isolation
def test_other_business_record_is_404_for_owner(sign_up_owner):
    # Behaviour: the Owner passes the Role check, then the tenant filter answers 404 (FR-11).
    a, _ = sign_up_owner()
    _, b_id = sign_up_owner()
    assert_not_found(probe_client(a).post(f"/probe/team/{membership_of(b_id)}/deactivate"))
    assert membership_is_active(b_id)

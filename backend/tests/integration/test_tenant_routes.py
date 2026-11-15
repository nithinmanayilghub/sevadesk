# Integration tests: a logged-in route runs inside its own Business's tenant scope (story 2.3, AD-3).
# The routes live in a test-only probe app (probe_app.py); the cookie comes from a real sign-up.
import uuid

import pytest
from fastapi.testclient import TestClient
from tests.integration.conftest import assert_not_found, membership_is_active, membership_of
from tests.integration.probe_app import build_probe_app, probe_client

pytestmark = pytest.mark.isolation


def test_logged_in_route_runs_in_own_business(sign_up_owner):
    # Behaviour: a logged-in route sees the Owner's own Business.
    owner, business_id = sign_up_owner()
    response = probe_client(owner).get("/probe/business")
    assert response.status_code == 200
    assert response.json() == {"business_id": str(business_id)}


def test_two_owners_each_see_their_own_business(sign_up_owner):
    # Behaviour: two Owners never see each other's Business.
    (a, a_id), (b, b_id) = sign_up_owner(), sign_up_owner()
    assert probe_client(a).get("/probe/business").json()["business_id"] == str(a_id)
    assert probe_client(b).get("/probe/business").json()["business_id"] == str(b_id)


def test_route_without_actor_has_no_business(sign_up_owner):
    # Behaviour: a valid cookie is not enough; only ActorDep sets the Business.
    owner, _ = sign_up_owner()
    response = probe_client(owner, raise_server_exceptions=False).get("/probe/no-actor")
    assert response.status_code == 500


def test_probe_without_cookie_is_401(make_client):
    # Behaviour: no cookie, no Actor, no Business: 401.
    response = TestClient(build_probe_app(), base_url="https://testserver").get("/probe/business")
    assert response.status_code == 401


def test_read_own_record_by_id_is_200(sign_up_owner):
    # Behaviour: a shop can read its own row by id.
    a, a_id = sign_up_owner()
    response = probe_client(a).get(f"/probe/memberships/{membership_of(a_id)}")
    assert response.status_code == 200
    assert response.json() == {"id": str(membership_of(a_id))}


def test_read_other_business_by_id_is_404(sign_up_owner):
    # Behaviour: shop A asks for shop B's row by id and gets our "not found" error.
    (a, _), (_, b_id) = sign_up_owner(), sign_up_owner()
    assert_not_found(probe_client(a).get(f"/probe/memberships/{membership_of(b_id)}"))


def test_write_own_record_changes_it(sign_up_owner):
    # Behaviour (positive control): the probe write really writes, so the next test means something.
    a, a_id = sign_up_owner()
    assert probe_client(a).post(f"/probe/memberships/{membership_of(a_id)}/deactivate").status_code == 204
    assert membership_is_active(a_id) is False


def test_write_other_business_by_id_is_404_and_changes_nothing(sign_up_owner):
    # Behaviour: shop A tries to change shop B's row: "not found", and B's row stays the same.
    (a, _), (b, b_id) = sign_up_owner(), sign_up_owner()
    assert_not_found(probe_client(a).post(f"/probe/memberships/{membership_of(b_id)}/deactivate"))
    assert membership_is_active(b_id) is True
    assert b.get("/api/v1/me").status_code == 200


def test_read_missing_id_is_same_404(sign_up_owner):
    # Behaviour: an id that does not exist gets the exact same 404 as another shop's id.
    a, _ = sign_up_owner()
    missing_id = uuid.uuid7()
    assert_not_found(probe_client(a).get(f"/probe/memberships/{missing_id}"))

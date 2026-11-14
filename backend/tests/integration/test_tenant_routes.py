# Integration tests: a logged-in route runs inside its own Business's tenant scope (story 2.3, AD-3).
# The routes live in a test-only probe app (probe_app.py); the cookie comes from a real sign-up.
import pytest
from fastapi.testclient import TestClient
from tests.integration.probe_app import build_probe_app

pytestmark = pytest.mark.isolation


def probe_client(owner: TestClient, **kwargs) -> TestClient:
    """A client for the probe app that carries the Owner's session cookie."""
    return TestClient(
        build_probe_app(),
        base_url="https://testserver",
        headers={"Origin": "https://testserver"},
        cookies=owner.cookies,
        **kwargs,
    )


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

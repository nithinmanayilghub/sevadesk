# The setup status (Owner only) and the public Chat Page API (story 3.3, FR-14).
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.integration.conftest import assert_not_found, set_owner_roles
from tests.integration.test_tenant_isolation import HOURS_WEEK, SERVICE, _add_service, _put_week, _setup

from app.core.tenancy import current_business_id
from app.modules.business.dependencies import ChatBusinessDep


def _set_active(owner: TestClient, service: dict, is_active: bool) -> None:
    body = {key: service[key] for key in ("name", "duration_minutes", "price_paise")}
    response = owner.put(f"/api/v1/services/{service['service_id']}", json={**body, "is_active": is_active})
    assert response.status_code == 200, response.text


def _chat_page(client: TestClient, slug: str) -> dict:
    response = client.get(f"/api/v1/chat/{slug}")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- GET /api/v1/setup


def test_new_business_setup_is_not_done(sign_up_owner):
    owner, _ = sign_up_owner()
    setup = _setup(owner)
    assert setup["has_services"] is False
    assert setup["has_working_hours"] is False
    assert setup["chat_slug"].startswith("test-shop-")


def test_setup_counts_only_active_services(sign_up_owner):
    owner, _ = sign_up_owner()
    service = _add_service(owner)
    _set_active(owner, service, False)
    assert _setup(owner)["has_services"] is False
    _set_active(owner, service, True)
    assert _setup(owner)["has_services"] is True


def test_setup_sees_working_hours(sign_up_owner):
    owner, _ = sign_up_owner()
    _put_week(owner, {**{day: None for day in HOURS_WEEK}, "monday": {"start_time": "10:00", "end_time": "18:00"}})
    assert _setup(owner)["has_working_hours"] is True


def test_setup_is_owner_only(sign_up_owner):
    owner, business_id = sign_up_owner()
    set_owner_roles(business_id, ["staff"])
    assert owner.get("/api/v1/setup").status_code == 403


# ---------------------------------------------------------------- GET /api/v1/chat/{chat_slug}


def test_chat_page_needs_no_login(sign_up_owner, client):
    owner, _ = sign_up_owner()
    page = _chat_page(client, _setup(owner)["chat_slug"])  # client: no session cookie
    assert page["business_name"] == "Test Shop"


def test_chat_page_lists_active_services(sign_up_owner, client):
    owner, _ = sign_up_owner()
    _add_service(owner)
    owner.post("/api/v1/services", json={**SERVICE, "name": "AC service", "duration_minutes": 90})
    services = _chat_page(client, _setup(owner)["chat_slug"])["services"]
    assert services == [
        {"name": "Fan repair", "duration_minutes": 60, "price_paise": 49900},
        {"name": "AC service", "duration_minutes": 90, "price_paise": 49900},
    ]  # oldest first, and no ids


def test_inactive_services_are_hidden(sign_up_owner, client):
    owner, _ = sign_up_owner()
    _add_service(owner)
    old_job = owner.post("/api/v1/services", json={**SERVICE, "name": "Old job"}).json()
    _set_active(owner, old_job, False)
    services = _chat_page(client, _setup(owner)["chat_slug"])["services"]
    assert [s["name"] for s in services] == ["Fan repair"]


@pytest.mark.parametrize(
    ("add_service", "add_hours", "taking"),
    [(False, False, False), (True, False, False), (False, True, False), (True, True, True)],
    ids=["none", "services only", "hours only", "both"],
)
def test_not_taking_requests_without_services_or_hours(sign_up_owner, client, add_service, add_hours, taking):
    owner, _ = sign_up_owner()
    if add_service:
        _add_service(owner)
    if add_hours:
        _put_week(owner, HOURS_WEEK)
    assert _chat_page(client, _setup(owner)["chat_slug"])["taking_requests"] is taking


@pytest.mark.parametrize("slug", ["no-such-slug", "%00", "a" * 500, "bad slug!"], ids=["unknown", "nul", "long", "bad"])
def test_bad_slug_is_not_found(client, slug):
    assert_not_found(client.get(f"/api/v1/chat/{slug}"))


def test_slug_is_case_insensitive(sign_up_owner, client):
    owner, _ = sign_up_owner()
    page = _chat_page(client, _setup(owner)["chat_slug"].upper())
    assert page["business_name"] == "Test Shop"


def test_route_runs_inside_the_slug_business(sign_up_owner):
    # The shared public-chat step (business/dependencies.py, story 4.1): any route that uses
    # ChatBusinessDep runs inside the slug's Business, so tenant repositories just work.
    probe = FastAPI()

    @probe.get("/probe/{chat_slug}")
    def where_am_i(business: ChatBusinessDep) -> dict:
        return {"current": str(current_business_id()), "business_id": str(business.business_id)}

    owner, business_id = sign_up_owner()
    answer = TestClient(probe).get(f"/probe/{_setup(owner)['chat_slug']}").json()
    assert answer == {"current": str(business_id), "business_id": str(business_id)}


def test_deactivating_the_only_service_stops_requests(sign_up_owner, client):
    owner, _ = sign_up_owner()
    service = _add_service(owner)
    _put_week(owner, HOURS_WEEK)
    slug = _setup(owner)["chat_slug"]
    assert _chat_page(client, slug)["taking_requests"] is True  # before: both facts true

    _set_active(owner, service, is_active=False)
    page = _chat_page(client, slug)
    assert page["taking_requests"] is False
    assert page["services"] == []

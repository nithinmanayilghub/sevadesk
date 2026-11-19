# Integration tests: Settings → Services API (story 3.1, FR-10, FR-12, AR-5).
# The Owner adds, edits, deactivates and reactivates Services. Every rule answers 422 with
# the message next to its field (UX-DR33). Staff and Technicians get 403 on every route.
import uuid

import pytest
from sqlalchemy.orm import Session
from tests.integration.conftest import assert_not_found

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.modules.business import service as business_service

FORBIDDEN_BODY = {"error": {"code": "forbidden", "message": "You don't have access to this."}}
FAN = {"name": "Fan repair", "duration_minutes": 60, "price_paise": 49900, "is_active": True}
PRICE_MISSING = "Enter a Price in rupees, for example 499."


def field_errors(response) -> dict[str, str]:
    """The 422 field errors as {field: message}."""
    assert response.status_code == 422, response.text
    return {item["field"]: item["message"] for item in response.json()["error"]["fields"]}


def services(client) -> list[dict]:
    response = client.get("/api/v1/services")
    assert response.status_code == 200, response.text
    return response.json()["services"]


def add(client, body: dict = FAN) -> dict:
    response = client.post("/api/v1/services", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def put(client, service_id, body: dict):
    return client.put(f"/api/v1/services/{service_id}", json=body)


def without(body: dict, key: str) -> dict:
    return {k: v for k, v in body.items() if k != key}


def test_owner_adds_a_service_saved_active(sign_up_owner):
    owner, _ = sign_up_owner()
    created = add(owner)
    assert without(created, "service_id") == FAN
    assert services(owner) == [created]


@pytest.mark.parametrize("body", [without(FAN, "price_paise"), {**FAN, "price_paise": None}])
def test_missing_price_is_refused_next_to_the_field(sign_up_owner, body):
    owner, _ = sign_up_owner()
    assert field_errors(owner.post("/api/v1/services", json=body)) == {"price_paise": PRICE_MISSING}
    assert services(owner) == []


@pytest.mark.parametrize("minutes", [29, 481])
def test_duration_outside_30_to_480_is_refused(sign_up_owner, minutes):
    owner, _ = sign_up_owner()
    response = owner.post("/api/v1/services", json={**FAN, "duration_minutes": minutes})
    assert field_errors(response) == {"duration_minutes": "Use 30 to 480 minutes."}


def test_duration_edges_and_missing_duration(sign_up_owner):
    owner, _ = sign_up_owner()
    add(owner, {**FAN, "duration_minutes": 30})
    add(owner, {**FAN, "duration_minutes": 480})
    response = owner.post("/api/v1/services", json=without(FAN, "duration_minutes"))
    assert field_errors(response) == {"duration_minutes": "Enter a duration in minutes."}


def test_price_zero_is_refused(sign_up_owner):
    owner, _ = sign_up_owner()
    response = owner.post("/api/v1/services", json={**FAN, "price_paise": 0})
    assert field_errors(response) == {"price_paise": "Enter a Price above ₹0."}


@pytest.mark.parametrize("paise", [100_000_001, 2**31, 10**15])
def test_price_above_cap_is_refused(sign_up_owner, paise):
    # 2**31 is above the Postgres integer limit: it must be a 422, never a 500.
    owner, _ = sign_up_owner()
    response = owner.post("/api/v1/services", json={**FAN, "price_paise": paise})
    assert field_errors(response) == {"price_paise": "Use at most ₹10,00,000."}


def test_price_at_cap_is_allowed(sign_up_owner):
    owner, _ = sign_up_owner()
    assert add(owner, {**FAN, "price_paise": 100_000_000})["price_paise"] == 100_000_000


@pytest.mark.parametrize("value", [True, "499", 499.0])
def test_non_integer_numbers_are_refused(sign_up_owner, value):
    # Without strict ints, JSON true would be saved as 1 paise.
    owner, _ = sign_up_owner()
    assert "price_paise" in field_errors(owner.post("/api/v1/services", json={**FAN, "price_paise": value}))
    assert services(owner) == []


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("   ", "Enter a name for the Service."),
        ("Fan\x00", "Enter a name for the Service."),  # Postgres cannot store NUL: a field error, not a 500
        ("x" * 101, "Use at most 100 characters."),
    ],
)
def test_blank_long_or_nul_name_is_refused(sign_up_owner, name, message):
    owner, _ = sign_up_owner()
    assert field_errors(owner.post("/api/v1/services", json={**FAN, "name": name})) == {"name": message}


def test_missing_is_active_is_refused(sign_up_owner):
    # A full replace must not quietly turn a Service back on.
    owner, _ = sign_up_owner()
    created = add(owner, {**FAN, "is_active": False})
    assert "is_active" in field_errors(put(owner, created["service_id"], without(FAN, "is_active")))
    assert services(owner)[0]["is_active"] is False


def test_owner_edits_a_service(sign_up_owner):
    owner, _ = sign_up_owner()
    created = add(owner)
    change = {"name": "Wiring check", "duration_minutes": 90, "price_paise": 79900, "is_active": True}
    response = put(owner, created["service_id"], change)
    assert response.status_code == 200, response.text
    assert response.json() == {**change, "service_id": created["service_id"]}
    assert services(owner) == [response.json()]


def test_edit_without_price_is_refused_and_keeps_old_row(sign_up_owner):
    owner, _ = sign_up_owner()
    created = add(owner)
    response = put(owner, created["service_id"], {**FAN, "price_paise": None})
    assert field_errors(response) == {"price_paise": PRICE_MISSING}
    assert services(owner) == [created]


def active_services(business_id: uuid.UUID) -> list:
    """What the Chat Page and the Agent will see (the business front door)."""
    with Session(get_engine()) as session, tenant_scope(business_id):
        return business_service.list_active_services(session)


def test_deactivated_service_is_no_longer_offered(sign_up_owner):
    owner, business_id = sign_up_owner()
    created = add(owner)
    assert [s.name for s in active_services(business_id)] == ["Fan repair"]

    assert put(owner, created["service_id"], {**FAN, "is_active": False}).status_code == 200
    assert services(owner)[0]["is_active"] is False  # the Owner still sees it, marked inactive
    assert active_services(business_id) == []  # but it is no longer offered

    assert put(owner, created["service_id"], FAN).status_code == 200
    assert [s.name for s in active_services(business_id)] == ["Fan repair"]


def test_activating_without_price_is_refused(sign_up_owner):
    owner, _ = sign_up_owner()
    created = add(owner, {**FAN, "is_active": False})
    response = put(owner, created["service_id"], {**FAN, "price_paise": None, "is_active": True})
    assert field_errors(response) == {"price_paise": PRICE_MISSING}
    assert services(owner)[0]["is_active"] is False


@pytest.mark.parametrize("roles", [["staff"], ["technician"], ["staff", "technician"]])
def test_staff_and_technician_get_403_on_service_routes(sign_up_owner, invite_member, roles):
    owner, _ = sign_up_owner()
    created = add(owner)
    member = invite_member(owner, roles).client

    for response in (
        member.get("/api/v1/services"),
        member.post("/api/v1/services", json=FAN),
        put(member, created["service_id"], {**FAN, "price_paise": 1}),
    ):
        assert response.status_code == 403, response.text
        assert response.json() == FORBIDDEN_BODY
    assert services(owner) == [created]  # nothing changed, nothing added


def test_role_check_runs_before_lookup(sign_up_owner, invite_member):
    # A missing id still answers 403, so a 403 never tells Staff whether a record exists.
    owner, _ = sign_up_owner()
    member = invite_member(owner, ["staff"]).client
    assert put(member, uuid.uuid4(), FAN).status_code == 403


def test_logged_out_caller_gets_401(make_client):
    stranger = make_client()
    assert stranger.get("/api/v1/services").status_code == 401
    assert stranger.post("/api/v1/services", json=FAN).status_code == 401


def test_unknown_service_id_is_404(sign_up_owner):
    owner, _ = sign_up_owner()
    assert_not_found(put(owner, uuid.uuid4(), FAN))

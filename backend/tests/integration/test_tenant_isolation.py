# The tenant-isolation suite (FR-11): every API endpoint is listed here, once.
#
# HOW TO ADD A NEW ENDPOINT
# - It touches one Business's data (it uses ActorDep or has a {path param}):
#   add a check to ISOLATION_CHECKS. The check calls the endpoint as Owner A with
#   Owner B's ids, uses assert_not_found(), and proves B's row did not change.
# - It touches no Business's data (needs_isolation_check() is False):
#   add it to NO_TENANT_DATA with a one-line reason.
# A new endpoint in neither dict fails test_every_endpoint_is_listed_once.
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from tests.integration.conftest import _make_client, assert_not_found, set_owner_roles

from app.core.db import get_engine
from app.main import app
from app.modules.accounts.dependencies import actor_in_tenant_scope
from app.modules.accounts.models import Invite
from app.modules.business.models import ClosedDay, Service
from app.modules.inbox.models import Conversation

pytestmark = pytest.mark.isolation

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}

# Pages FastAPI adds itself (docs and the schema). The only routes allowed outside the schema.
FRAMEWORK_PATHS = {"/api/openapi.json", "/api/docs", "/docs/oauth2-redirect", "/redoc"}


@dataclass
class TwoOwners:
    """Two logged-in Owners, each in their own new Business."""

    a: TestClient
    a_business_id: uuid.UUID
    b: TestClient
    b_business_id: uuid.UUID


@pytest.fixture
def two_owners(sign_up_owner) -> TwoOwners:
    (a, a_id), (b, b_id) = sign_up_owner(), sign_up_owner()
    return TwoOwners(a=a, a_business_id=a_id, b=b, b_business_id=b_id)


def check_me(owners: TwoOwners) -> None:
    # Give B different roles first (A keeps "owner, technician" from sign-up), so a mix-up shows.
    set_owner_roles(owners.b_business_id, ["owner"])
    assert owners.a.get("/api/v1/me").json()["roles"] == ["owner", "technician"]
    assert owners.b.get("/api/v1/me").json()["roles"] == ["owner"]


def check_theme(owners: TwoOwners) -> None:
    # A saves "dark": A sees it, B stays on "system".
    assert owners.a.put("/api/v1/me/theme", json={"theme": "dark"}).status_code == 204
    assert owners.a.get("/api/v1/me").json()["theme"] == "dark"
    assert owners.b.get("/api/v1/me").json()["theme"] == "system"


def check_logout(owners: TwoOwners) -> None:
    # A logs out: only A's session ends. B stays logged in.
    assert owners.a.post("/api/v1/logout").status_code == 204
    assert owners.a.get("/api/v1/me").status_code == 401
    assert owners.b.get("/api/v1/me").status_code == 200


def _invite_business_ids() -> dict[str, uuid.UUID]:
    # A direct database read: which Business owns each invite, by email.
    with Session(get_engine()) as session:
        return {invite.email: invite.business_id for invite in session.scalars(select(Invite))}


def check_create_invite(owners: TwoOwners) -> None:
    # A's invite belongs to A's Business; B gets nothing new.
    email = f"{uuid.uuid4().hex}@example.com"
    body = {"email": email, "roles": ["staff"]}
    assert owners.a.post("/api/v1/team/invites", json=body).status_code == 201
    owned_by = _invite_business_ids()
    assert owned_by[email] == owners.a_business_id
    assert owners.b_business_id not in owned_by.values()


def _owner_membership_id(client: TestClient) -> uuid.UUID:
    [me] = [m for m in client.get("/api/v1/team").json()["members"] if m["is_you"]]
    return uuid.UUID(me["membership_id"])


def check_list_team(owners: TwoOwners) -> None:
    # A's team list holds only A's own member: none of B's.
    a_members = owners.a.get("/api/v1/team").json()["members"]
    b_ids = {m["membership_id"] for m in owners.b.get("/api/v1/team").json()["members"]}
    assert len(a_members) == 1
    assert not {m["membership_id"] for m in a_members} & b_ids


def check_update_member(owners: TwoOwners) -> None:
    # A tries to change B's Owner (a valid body): 404, and B's Roles stay the same.
    b_owner_id = _owner_membership_id(owners.b)
    assert_not_found(owners.a.patch(f"/api/v1/team/members/{b_owner_id}", json={"roles": ["owner"]}))
    assert owners.b.get("/api/v1/me").json()["roles"] == ["owner", "technician"]


SERVICE = {"name": "Fan repair", "duration_minutes": 60, "price_paise": 49900, "is_active": True}


def _add_service(client: TestClient) -> dict:
    response = client.post("/api/v1/services", json=SERVICE)
    assert response.status_code == 201, response.text
    return response.json()


def _services(client: TestClient) -> list[dict]:
    return client.get("/api/v1/services").json()["services"]


def check_list_services(owners: TwoOwners) -> None:
    # A's list holds only A's own Service: none of B's.
    a_service, _ = _add_service(owners.a), _add_service(owners.b)
    assert [s["service_id"] for s in _services(owners.a)] == [a_service["service_id"]]


def check_create_service(owners: TwoOwners) -> None:
    # A's new Service belongs to A's Business; B gets nothing new.
    created = _add_service(owners.a)
    with Session(get_engine()) as session:
        row = session.get(Service, uuid.UUID(created["service_id"]))
        assert row.business_id == owners.a_business_id
    assert _services(owners.b) == []


def check_replace_service(owners: TwoOwners) -> None:
    # A tries to change B's Service (a valid body): 404, and B's Service stays the same.
    b_service = _add_service(owners.b)
    change = {**SERVICE, "price_paise": 1, "is_active": False}
    assert_not_found(owners.a.put(f"/api/v1/services/{b_service['service_id']}", json=change))
    assert _services(owners.b) == [b_service]


HOURS_WEEK = {
    **{
        day: {"start_time": "10:00", "end_time": "18:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
    },
    "sunday": None,
}


def _put_week(client: TestClient, body: dict) -> dict:
    response = client.put("/api/v1/working-hours", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def check_get_working_hours(owners: TwoOwners) -> None:
    # B saves a week first; A's week is still empty (every day closed).
    _put_week(owners.b, HOURS_WEEK)
    a_week = owners.a.get("/api/v1/working-hours").json()
    assert all(a_week[day] is None for day in HOURS_WEEK)


def check_replace_working_hours(owners: TwoOwners) -> None:
    # A replaces A's own week; B's saved week stays the same.
    b_week = _put_week(owners.b, HOURS_WEEK)
    _put_week(owners.a, {day: None for day in HOURS_WEEK})
    assert owners.b.get("/api/v1/working-hours").json() == b_week


def _close_day(client: TestClient, day: str = "2099-12-25") -> dict:
    # A far-future date, so "today" never matters here.
    response = client.post("/api/v1/closed-days", json={"day": day})
    assert response.status_code == 201, response.text
    return response.json()


def _closed_days(client: TestClient) -> list[dict]:
    return client.get("/api/v1/closed-days").json()["closed_days"]


def check_list_closed_days(owners: TwoOwners) -> None:
    # B closes a day first; A's list stays empty.
    _close_day(owners.b)
    assert _closed_days(owners.a) == []


def check_add_closed_day(owners: TwoOwners) -> None:
    # A's new closed day belongs to A's Business; B gets nothing new.
    created = _close_day(owners.a)
    with Session(get_engine()) as session:
        row = session.get(ClosedDay, uuid.UUID(created["closed_day_id"]))
        assert row.business_id == owners.a_business_id
    assert _closed_days(owners.b) == []


def check_delete_closed_day(owners: TwoOwners) -> None:
    # A tries to delete B's closed day: 404, and B's row stays.
    b_day = _close_day(owners.b)
    assert_not_found(owners.a.delete(f"/api/v1/closed-days/{b_day['closed_day_id']}"))
    assert _closed_days(owners.b) == [b_day]


def _setup(client: TestClient) -> dict:
    response = client.get("/api/v1/setup")
    assert response.status_code == 200, response.text
    return response.json()


def check_get_setup(owners: TwoOwners) -> None:
    # B finishes setup; A's setup is still not done, and A gets A's own slug.
    _add_service(owners.b)
    _put_week(owners.b, HOURS_WEEK)
    a_setup, b_setup = _setup(owners.a), _setup(owners.b)
    assert (a_setup["has_services"], a_setup["has_working_hours"]) == (False, False)
    assert a_setup["chat_slug"] != b_setup["chat_slug"]


def _chat_service_names(client: TestClient, slug: str) -> list[str]:
    response = client.get(f"/api/v1/chat/{slug}")
    assert response.status_code == 200, response.text
    return [s["name"] for s in response.json()["services"]]


def check_get_chat_page(owners: TwoOwners) -> None:
    # This check expects 200 on purpose, not assert_not_found: the Chat Page is public.
    # The proof is that the SLUG, not the session cookie, picks the Business (AD-3 b).
    owners.a.post("/api/v1/services", json={**SERVICE, "name": "A only"})
    owners.b.post("/api/v1/services", json={**SERVICE, "name": "B only"})
    a_slug, b_slug = _setup(owners.a)["chat_slug"], _setup(owners.b)["chat_slug"]
    # Owner A is logged in, and opens B's link: only B's Services.
    assert _chat_service_names(owners.a, b_slug) == ["B only"]
    assert _chat_service_names(owners.a, a_slug) == ["A only"]


def _visitor_send(visitor: TestClient, slug: str, body: str) -> None:
    payload = {"body": body, "client_message_id": str(uuid.uuid4())}
    response = visitor.post(f"/api/v1/chat/{slug}/messages", json=payload)
    assert response.status_code == 201, response.text


def _conversations_in(business_id: uuid.UUID) -> int:
    # A direct database read: how many Conversations this Business has.
    with Session(get_engine()) as session:
        return session.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.business_id == business_id)
        )


def check_list_chat_messages(owners: TwoOwners) -> None:
    # Public too: the slug picks the Business, the cookie picks the chat. ONE browser (one
    # cookie for every slug) writes to B, then opens A's Chat Page: none of B's Messages.
    visitor = _make_client()
    a_slug, b_slug = _setup(owners.a)["chat_slug"], _setup(owners.b)["chat_slug"]
    _visitor_send(visitor, b_slug, "for B only")
    assert visitor.get(f"/api/v1/chat/{a_slug}/messages").json() == {
        "changed": True,
        "messages": [],
        "snapshot": None,
        "cursor": None,
    }
    b_answer = visitor.get(f"/api/v1/chat/{b_slug}/messages").json()
    assert [m["body"] for m in b_answer["messages"]] == ["for B only"]
    # B's cursor on A's slug (story 4.2): still A's empty answer, never B's "no change".
    assert visitor.get(f"/api/v1/chat/{a_slug}/messages", params={"cursor": b_answer["cursor"]}).json() == {
        "changed": True,
        "messages": [],
        "snapshot": None,
        "cursor": None,
    }


def check_send_chat_message(owners: TwoOwners) -> None:
    # The same browser writes to both: each Business gets its own Conversation, nothing mixes.
    visitor = _make_client()
    a_slug, b_slug = _setup(owners.a)["chat_slug"], _setup(owners.b)["chat_slug"]
    _visitor_send(visitor, b_slug, "to B")
    _visitor_send(visitor, a_slug, "to A")
    assert (_conversations_in(owners.a_business_id), _conversations_in(owners.b_business_id)) == (1, 1)
    assert [m["seq"] for m in visitor.get(f"/api/v1/chat/{a_slug}/messages").json()["messages"]] == [1]


def _inbox_ids(client: TestClient) -> list[str]:
    response = client.get("/api/v1/inbox/conversations")
    assert response.status_code == 200, response.text
    return [row["conversation_id"] for row in response.json()["conversations"]]


def check_list_inbox(owners: TwoOwners) -> None:
    # B's visitor writes first: A's Inbox stays empty. Then A's visitor writes: A sees only that one.
    a_slug, b_slug = _setup(owners.a)["chat_slug"], _setup(owners.b)["chat_slug"]
    _visitor_send(_make_client(), b_slug, "for B only")
    assert _inbox_ids(owners.a) == []
    _visitor_send(_make_client(), a_slug, "for A")
    b_ids = _inbox_ids(owners.b)
    a_ids = _inbox_ids(owners.a)
    assert len(a_ids) == 1 and len(b_ids) == 1 and a_ids != b_ids


def check_count_needs_human(owners: TwoOwners) -> None:
    # B has one Needs Human chat; A's count stays 0.
    _visitor_send(_make_client(), _setup(owners.b)["chat_slug"], "help")
    with get_engine().begin() as connection:
        connection.execute(
            update(Conversation).where(Conversation.business_id == owners.b_business_id).values(state="handoff")
        )
    assert owners.b.get("/api/v1/inbox/needs-human-count").json() == {"count": 1}
    assert owners.a.get("/api/v1/inbox/needs-human-count").json() == {"count": 0}


def _b_chat(owners: TwoOwners) -> str:
    """One Customer chat in Business B. Returns its id, as B's own Inbox shows it."""
    _visitor_send(_make_client(), _setup(owners.b)["chat_slug"], "for B only")
    (conversation_id,) = _inbox_ids(owners.b)
    return conversation_id


def _b_chat_unchanged(owners: TwoOwners, conversation_id: str) -> None:
    # B still sees exactly its one Customer Message, and the Agent still replies.
    answer = owners.b.get(f"/api/v1/inbox/conversations/{conversation_id}/messages").json()
    assert [m["author_type"] for m in answer["messages"]] == ["customer"]
    assert answer["snapshot"] == {"conversation_state": "agent"}


def check_poll_inbox_conversation(owners: TwoOwners) -> None:
    # A cannot read B's chat, with or without a cursor; B can.
    conversation_id = _b_chat(owners)
    url = f"/api/v1/inbox/conversations/{conversation_id}/messages"
    b_cursor = owners.b.get(url).json()["cursor"]
    assert_not_found(owners.a.get(url))
    assert_not_found(owners.a.get(url, params={"cursor": b_cursor}))
    _b_chat_unchanged(owners, conversation_id)


def _check_a_cannot_post(owners: TwoOwners, suffix: str, body: dict | None = None) -> None:
    conversation_id = _b_chat(owners)
    assert_not_found(owners.a.post(f"/api/v1/inbox/conversations/{conversation_id}/{suffix}", json=body))
    _b_chat_unchanged(owners, conversation_id)


def check_send_inbox_reply(owners: TwoOwners) -> None:
    _check_a_cannot_post(owners, "messages", {"body": "hi", "client_message_id": str(uuid.uuid4())})


def check_take_over_conversation(owners: TwoOwners) -> None:
    _check_a_cannot_post(owners, "take-over")


def check_give_back_conversation(owners: TwoOwners) -> None:
    # Give back changes nothing on an agent chat anyway, so first B takes it over itself.
    conversation_id = _b_chat(owners)
    assert owners.b.post(f"/api/v1/inbox/conversations/{conversation_id}/take-over").status_code == 200
    assert_not_found(owners.a.post(f"/api/v1/inbox/conversations/{conversation_id}/give-back"))
    answer = owners.b.get(f"/api/v1/inbox/conversations/{conversation_id}/messages").json()
    assert answer["snapshot"] == {"conversation_state": "handoff"}  # still B's handoff


def check_get_conversation_customer(owners: TwoOwners) -> None:
    # A cannot read B's Customer through B's chat id; B can.
    conversation_id = _b_chat(owners)
    assert_not_found(owners.a.get(f"/api/v1/inbox/conversations/{conversation_id}/customer"))
    assert owners.b.get(f"/api/v1/inbox/conversations/{conversation_id}/customer").status_code == 200


def check_delete_customer(owners: TwoOwners) -> None:
    # A cannot delete B's Customer: a 404, and B's chat is still all there.
    conversation_id = _b_chat(owners)
    customer_id = owners.b.get(f"/api/v1/inbox/conversations/{conversation_id}/customer").json()["customer_id"]
    assert_not_found(owners.a.delete(f"/api/v1/inbox/customers/{customer_id}"))
    _b_chat_unchanged(owners, conversation_id)


def check_list_free_slots(owners: TwoOwners) -> None:
    # A cannot read the Slots of B's Service: a 404, the same as for a Service that does not exist.
    b_service = _add_service(owners.b)
    _put_week(owners.b, HOURS_WEEK)
    assert_not_found(owners.a.get("/api/v1/bookings/slots", params={"service_id": b_service["service_id"]}))


NO_TENANT_DATA: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/hello"): "a fixed greeting; reads no Business data",
    ("GET", "/api/health"): "is the server up; reads no Business data",
    ("GET", "/api/health/worker"): "is the worker up; reads no Business data",
    ("POST", "/api/v1/signup"): "creates a brand-new Business; there is no other Business to reach",
    ("POST", "/api/v1/login"): "logs in by email and password; returns only the caller's own roles",
    ("POST", "/api/v1/invites/preview"): "no session; the Business comes from the secret token's own invite row",
    ("POST", "/api/v1/invites/accept"): "no session; the Business comes from the secret token's own invite row",
}

ISOLATION_CHECKS: dict[tuple[str, str], Callable[[TwoOwners], None]] = {
    ("GET", "/api/v1/me"): check_me,
    ("PUT", "/api/v1/me/theme"): check_theme,
    ("POST", "/api/v1/logout"): check_logout,
    ("POST", "/api/v1/team/invites"): check_create_invite,
    ("GET", "/api/v1/team"): check_list_team,
    ("PATCH", "/api/v1/team/members/{membership_id}"): check_update_member,
    ("GET", "/api/v1/services"): check_list_services,
    ("POST", "/api/v1/services"): check_create_service,
    ("PUT", "/api/v1/services/{service_id}"): check_replace_service,
    ("GET", "/api/v1/working-hours"): check_get_working_hours,
    ("PUT", "/api/v1/working-hours"): check_replace_working_hours,
    ("GET", "/api/v1/closed-days"): check_list_closed_days,
    ("POST", "/api/v1/closed-days"): check_add_closed_day,
    ("DELETE", "/api/v1/closed-days/{closed_day_id}"): check_delete_closed_day,
    ("GET", "/api/v1/setup"): check_get_setup,
    ("GET", "/api/v1/chat/{chat_slug}"): check_get_chat_page,
    ("GET", "/api/v1/chat/{chat_slug}/messages"): check_list_chat_messages,
    ("POST", "/api/v1/chat/{chat_slug}/messages"): check_send_chat_message,
    ("GET", "/api/v1/inbox/conversations"): check_list_inbox,
    ("GET", "/api/v1/inbox/needs-human-count"): check_count_needs_human,
    ("GET", "/api/v1/inbox/conversations/{conversation_id}/messages"): check_poll_inbox_conversation,
    ("POST", "/api/v1/inbox/conversations/{conversation_id}/messages"): check_send_inbox_reply,
    ("POST", "/api/v1/inbox/conversations/{conversation_id}/take-over"): check_take_over_conversation,
    ("POST", "/api/v1/inbox/conversations/{conversation_id}/give-back"): check_give_back_conversation,
    ("GET", "/api/v1/inbox/conversations/{conversation_id}/customer"): check_get_conversation_customer,
    ("DELETE", "/api/v1/inbox/customers/{customer_id}"): check_delete_customer,
    ("GET", "/api/v1/bookings/slots"): check_list_free_slots,
}


def api_operations(schema: dict) -> set[tuple[str, str]]:
    """Every (METHOD, path) in an OpenAPI schema. Skips non-method keys like "parameters"."""
    return {
        (method.upper(), path) for path, item in schema["paths"].items() for method in item if method in HTTP_METHODS
    }


def unlisted(operations: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """The operations that are in neither dict."""
    return operations - (NO_TENANT_DATA.keys() | ISOLATION_CHECKS.keys())


def _uses_actor(dependencies) -> bool:
    # Walk the whole dependency tree: ActorDep may hide inside another dependency.
    return any(dep.call is actor_in_tenant_scope or _uses_actor(dep.dependencies) for dep in dependencies)


def needs_isolation_check(route) -> bool:
    """True if the route works for one Business: it has a {path param} or uses ActorDep."""
    return "{" in route.path or _uses_actor(route.dependant.dependencies)


def api_routes():
    """Every API route with its full path. iter_route_contexts is how FastAPI itself
    finds routes inside included routers (app.routes only holds the router boxes)."""
    return [route for route in iter_route_contexts(app.routes) if isinstance(route.original_route, APIRoute)]


def test_every_endpoint_is_listed_once():
    assert not (NO_TENANT_DATA.keys() & ISOLATION_CHECKS.keys()), "listed twice"
    operations = api_operations(app.openapi())
    assert unlisted(operations) == set(), "new endpoint with no isolation check"
    assert (NO_TENANT_DATA.keys() | ISOLATION_CHECKS.keys()) - operations == set(), "listed endpoint no longer exists"


def test_unlisted_catches_a_new_endpoint():
    schema = {"paths": {"/api/v1/services/{service_id}": {"get": {}, "parameters": []}}}
    assert unlisted(api_operations(schema)) == {("GET", "/api/v1/services/{service_id}")}


def test_no_route_is_hidden_from_the_schema():
    # A route with include_in_schema=False, or added with add_route/mount, would skip the
    # list above. So every route the app really serves must also be in the schema.
    served = set()
    for route in iter_route_contexts(app.routes):
        if isinstance(route.original_route, APIRoute):
            served |= {(method, route.path) for method in route.methods}
        else:
            assert route.path in FRAMEWORK_PATHS, f"unexpected non-API route {route.path}"
    assert served == api_operations(app.openapi())


def test_tenant_endpoints_are_not_excused():
    for route in api_routes():
        if needs_isolation_check(route):
            for method in route.methods:
                assert (method, route.path) in ISOLATION_CHECKS, f"{method} {route.path} needs an isolation check"


@pytest.mark.parametrize("operation", sorted(ISOLATION_CHECKS), ids=" ".join)
def test_cross_business_access_fails(operation, two_owners):
    ISOLATION_CHECKS[operation](two_owners)

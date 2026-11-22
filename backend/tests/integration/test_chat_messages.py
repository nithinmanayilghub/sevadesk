# The public chat Message routes (story 4.1, FR-15, AD-16, NFR-5): read your own chat, and send.
# Each TestClient is one browser: it keeps its cookies, like a real one.
import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.integration.conftest import assert_not_found
from tests.integration.test_tenant_isolation import _setup

from app.core.db import get_engine
from app.core.redis_client import get_redis
from app.core.settings import get_settings
from app.main import app
from app.modules.inbox import service
from app.modules.inbox.models import Message, VisitorToken
from app.modules.inbox.webchat import VISITOR_COOKIE


def count(model, business_id: uuid.UUID) -> int:
    with Session(get_engine()) as session:
        return session.scalar(select(func.count()).select_from(model).where(model.business_id == business_id))


def messages_url(slug: str) -> str:
    return f"/api/v1/chat/{slug}/messages"


def post(client: TestClient, slug: str, body: str = "Fan not working", client_id: uuid.UUID | None = None):
    return client.post(messages_url(slug), json={"body": body, "client_message_id": str(client_id or uuid.uuid4())})


@dataclass
class Shop:
    slug: str
    business_id: uuid.UUID


@pytest.fixture
def shop(sign_up_owner) -> Shop:
    owner, business_id = sign_up_owner()
    return Shop(slug=_setup(owner)["chat_slug"], business_id=business_id)


@pytest.fixture
def slug(shop) -> str:
    return shop.slug


def test_first_visit_sets_an_httponly_visitor_cookie(client, slug, shop):
    response = client.get(messages_url(slug))
    assert response.status_code == 200, response.text
    assert response.json() == {"messages": []}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{VISITOR_COOKIE}=")
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert flag in cookie
    assert count(VisitorToken, shop.business_id) == 0  # a GET writes nothing (AD-5); the row comes with the first send


def test_second_visit_keeps_the_cookie(client, slug):
    client.get(messages_url(slug))
    assert "set-cookie" not in client.get(messages_url(slug)).headers


def test_send_then_return_sees_own_messages(client, make_client, slug):
    client.get(messages_url(slug))
    sent = post(client, slug)
    assert sent.status_code == 201, sent.text
    assert (sent.json()["seq"], sent.json()["author_type"], sent.json()["body"]) == (1, "customer", "Fan not working")
    assert [m["body"] for m in client.get(messages_url(slug)).json()["messages"]] == ["Fan not working"]
    # Another browser opens the same Chat Page: it sees nothing of this chat.
    assert make_client().get(messages_url(slug)).json() == {"messages": []}


def test_send_without_cookie_still_works(client, slug):
    response = post(client, slug)
    assert response.status_code == 201, response.text
    assert response.headers["set-cookie"].startswith(f"{VISITOR_COOKIE}=")
    assert len(client.get(messages_url(slug)).json()["messages"]) == 1  # the new cookie found it


def test_duplicate_send_returns_the_same_message(client, slug, shop):
    client_id = uuid.uuid4()
    first, again = post(client, slug, client_id=client_id), post(client, slug, client_id=client_id)
    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()
    assert count(Message, shop.business_id) == 1


@pytest.mark.parametrize("method", ["get", "post"])
def test_unknown_slug_is_not_found(client, method):
    if method == "get":
        assert_not_found(client.get(messages_url("no-such-slug")))
    else:
        assert_not_found(post(client, "no-such-slug"))


def test_bad_body_is_422(client, slug):
    response = post(client, slug, body="   ")
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [{"field": "body", "message": "Write a message first."}]


def test_nul_in_body_is_422(client, slug, shop):
    response = post(client, slug, body="hi\u0000")
    assert response.status_code == 422
    assert response.json()["error"]["fields"][0]["field"] == "body"
    assert count(Message, shop.business_id) == 0


def test_ip_limit_returns_429(client, slug, shop, monkeypatch):
    monkeypatch.setattr(service, "CHAT_SEND_IP_LIMIT", 2)
    assert [post(client, slug).status_code for _ in range(2)] == [201, 201]
    response = post(client, slug)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_messages"
    assert int(response.headers["Retry-After"]) > 0
    assert count(Message, shop.business_id) == 2


def test_send_fails_closed_without_redis(make_client, slug, shop, monkeypatch):
    # No counter = no protection, so we refuse (503) rather than let spam through.
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # port 1 refuses at once
    get_settings.cache_clear()  # settings are cached too: clear both, as test_login does
    get_redis.cache_clear()
    response = post(make_client(raise_server_exceptions=False), slug)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"
    assert count(Message, shop.business_id) == 0


@pytest.mark.parametrize("value", ["x" * 5000, "a", "!" * 43], ids=["huge", "short", "bad-characters"])
def test_bad_cookie_is_a_new_visitor(slug, value):
    # A cookie we did not make is ignored: the browser gets a fresh token, never a 500.
    # A fresh client with the cookie in the header, so no other cookie with this name is in its jar.
    browser = TestClient(app, base_url="https://testserver")
    response = browser.get(messages_url(slug), headers={"Cookie": f"{VISITOR_COOKIE}={value}"})
    assert response.status_code == 200, response.text
    assert response.headers["set-cookie"].startswith(f"{VISITOR_COOKIE}=")


def test_public_routes_take_no_conversation_id():
    # AR-10: a visitor is known only by the cookie. No id to guess, so none is accepted or sent.
    schema = app.openapi()
    for path, item in schema["paths"].items():
        if not path.startswith("/api/v1/chat/"):
            continue
        for operation in item.values():
            assert "conversation_id" not in {p["name"] for p in operation.get("parameters", [])}, path
    for name in ("SendMessageIn", "MessageOut", "ChatMessagesOut"):
        assert "conversation_id" not in schema["components"]["schemas"][name]["properties"], name

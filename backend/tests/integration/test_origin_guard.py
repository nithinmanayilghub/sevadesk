# Integration tests for the Origin guard (story 2.2, AD-5 CSRF guard, D4).
# CSRF: another website makes YOUR browser send a request to us, with your cookie.
# The browser always says which site started a POST in the Origin header, and a page
# cannot fake it. So: a state-changing request must come with our own Origin.
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.modules.business.models import Business

GOOD = "correct horse battery"


def signup_body() -> dict:
    return {"business_name": "Shop", "email": f"{uuid.uuid4().hex}@example.com", "password": GOOD}


def business_count() -> int:
    with Session(get_engine()) as s:
        return s.scalar(select(func.count()).select_from(Business))


def no_origin_client(make_client):
    c = make_client()
    c.headers.pop("Origin")  # like curl or a script: no Origin header at all
    return c


def test_post_without_origin_is_refused(client, make_client):
    body = signup_body()
    assert client.post("/api/v1/signup", json=body).status_code == 201
    client.cookies.clear()
    bare = no_origin_client(make_client)
    for _ in range(6):
        response = bare.post("/api/v1/login", json={"email": body["email"], "password": "wrong horse battery"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "origin_refused"
    # Refused before the limiter ran: the account is not locked.
    assert client.post("/api/v1/login", json={"email": body["email"], "password": GOOD}).status_code == 200


def test_cross_site_signup_creates_nothing(client):
    before = business_count()
    response = client.post("/api/v1/signup", json=signup_body(), headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert business_count() == before


def test_null_origin_is_refused(client):
    # Browsers send "null" from sandboxed frames and some redirects.
    assert client.post("/api/v1/signup", json=signup_body(), headers={"Origin": "null"}).status_code == 403


def test_every_unsafe_method_is_guarded(make_client):
    bare = no_origin_client(make_client)
    for method in ("PUT", "PATCH", "DELETE"):
        # 403 from the guard, before routing (routing would say 405 Method Not Allowed).
        assert bare.request(method, "/api/v1/me").status_code == 403


def test_origin_case_does_not_matter(client):
    response = client.post("/api/v1/signup", json=signup_body(), headers={"Origin": "https://TestServer"})
    assert response.status_code == 201


def test_get_needs_no_origin(make_client):
    assert no_origin_client(make_client).get("/api/health").status_code != 403


def test_same_origin_post_works(client):
    assert client.post("/api/v1/signup", json=signup_body()).status_code == 201

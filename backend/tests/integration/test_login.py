# Integration tests for log-in, log-out and /me (story 2.2, FR-8, AD-5, NFR-5).
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.core.redis_client import get_redis
from app.core.session_cookie import SESSION_COOKIE
from app.core.settings import get_settings
from app.modules.accounts import service as accounts_service
from app.modules.accounts.models import Membership, User, UserSession

GOOD = "correct horse battery"
WRONG = "wrong horse battery!!"


def email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


def new_owner(client) -> str:
    """Sign up an Owner, then forget the cookie, so the test starts logged out."""
    address = email()
    assert (
        client.post("/api/v1/signup", json={"business_name": "Shop", "email": address, "password": GOOD}).status_code
        == 201
    )
    client.cookies.clear()
    return address


def log_in(client, address: str, password: str = GOOD, **headers):
    return client.post("/api/v1/login", json={"email": address, "password": password}, headers=headers)


def me_with(make_client, token: str):
    # A fresh "browser" that sends only this one cookie.
    return make_client().get("/api/v1/me", headers={"Cookie": f"{SESSION_COOKIE}={token}"})


def session_count() -> int:
    with Session(get_engine()) as s:
        return s.scalar(select(func.count()).select_from(UserSession))


def test_login_sets_a_safe_cookie(client):
    address = new_owner(client)
    response = log_in(client, address)
    assert response.status_code == 200
    assert response.json() == {"roles": ["owner", "technician"]}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert flag in cookie
    assert "Domain" not in cookie  # the __Host- prefix forbids a Domain


def test_signup_also_logs_in(client):
    response = client.post("/api/v1/signup", json={"business_name": "Shop", "email": email(), "password": GOOD})
    assert response.status_code == 201
    assert client.get("/api/v1/me").status_code == 200


def test_login_ends_the_old_session(client, make_client):
    first, second = new_owner(client), new_owner(client)
    log_in(client, first)
    old_token = client.cookies[SESSION_COOKIE]
    log_in(client, second)  # the same browser: it still sends the first cookie
    assert me_with(make_client, old_token).status_code == 401


def test_wrong_password_and_unknown_email_look_the_same(client):
    address = new_owner(client)
    wrong_password = log_in(client, address, WRONG)
    unknown_email = log_in(client, email(), WRONG)
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["code"] == "invalid_credentials"


def test_unknown_email_still_checks_one_password(client, monkeypatch):
    # Same work for both cases, so the reply time does not tell which emails exist.
    calls = []
    real = accounts_service.verify_password
    monkeypatch.setattr(accounts_service, "verify_password", lambda *a: calls.append(1) or real(*a))
    assert log_in(client, email(), WRONG).status_code == 401
    assert len(calls) == 1


def test_email_case_does_not_matter(client):
    address = new_owner(client)
    assert log_in(client, f"  {address.upper()} ").status_code == 200


def test_me_without_cookie_is_401(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_logout_kills_the_old_cookie(client, make_client):
    log_in(client, new_owner(client))
    token = client.cookies[SESSION_COOKIE]
    response = client.post("/api/v1/logout")
    assert response.status_code == 204
    assert SESSION_COOKIE not in client.cookies  # the browser is told to drop it
    assert me_with(make_client, token).status_code == 401  # a copied cookie is dead too


def test_account_limit(client):
    address = new_owner(client)
    for attempt in range(5):
        typed = address.upper() if attempt < 2 else address  # case does not give extra tries
        assert log_in(client, typed, WRONG).status_code == 401
    locked = log_in(client, address)  # the RIGHT password, but the account is locked
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "too_many_attempts"
    assert 0 < int(locked.headers["Retry-After"]) <= 900
    assert log_in(client, new_owner(client)).status_code == 200  # other accounts still work


def test_parallel_wrong_logins_are_capped(client, make_client):
    address = new_owner(client)

    def attempt(_):
        return log_in(make_client(), address, WRONG).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(attempt, range(10)))
    assert codes.count(401) <= 5
    assert codes.count(401) + codes.count(429) == 10


def test_ip_limit(client):
    for _ in range(20):
        assert log_in(client, email(), WRONG, **{"X-Forwarded-For": "203.0.113.7"}).status_code == 401
    assert log_in(client, email(), WRONG, **{"X-Forwarded-For": "203.0.113.7"}).status_code == 429
    assert log_in(client, email(), WRONG, **{"X-Forwarded-For": "203.0.113.8"}).status_code == 401


def test_success_clears_the_account_counter(client):
    address = new_owner(client)
    for _ in range(4):
        log_in(client, address, WRONG)
    assert log_in(client, address).status_code == 200
    client.cookies.clear()
    for _ in range(4):
        last = log_in(client, address, WRONG)
    assert last.status_code == 401


def test_no_raw_email_in_redis(client):
    log_in(client, email(), WRONG)
    keys = [key.decode() for key in get_redis().keys("*")]
    assert keys  # the failure was counted
    assert not any("@" in key for key in keys)


def test_redis_down_gives_503(client, monkeypatch):
    address = new_owner(client)
    before = session_count()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # port 1 refuses at once
    get_settings.cache_clear()  # settings are cached too: clear both, as test_health does
    get_redis.cache_clear()
    response = log_in(client, address)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"
    assert session_count() == before


def test_idle_session_returns_401(client):
    address = new_owner(client)
    log_in(client, address)
    with Session(get_engine()) as s, s.begin():
        user_id = s.scalars(select(User.id).where(User.email == address)).one()
        s.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(last_seen_at=datetime.now(UTC) - timedelta(days=8))
        )
    assert client.get("/api/v1/me").status_code == 401


def test_inactive_member_cannot_log_in(client):
    address = new_owner(client)
    with Session(get_engine()) as s, s.begin():
        user_id = s.scalars(select(User.id).where(User.email == address)).one()
        s.execute(update(Membership).where(Membership.user_id == user_id).values(is_active=False))
    response = log_in(client, address)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_field_errors(client):
    empty = log_in(client, "owner@shop.in", "")
    assert empty.status_code == 422
    assert empty.json()["error"]["fields"] == [{"field": "password", "message": "Enter your password."}]
    long = log_in(client, "owner@shop.in", "p" * 129)
    assert long.json()["error"]["fields"] == [{"field": "password", "message": "Use at most 128 characters."}]
    nul = log_in(client, "a\x00b@x.com", GOOD)
    assert nul.json()["error"]["fields"] == [{"field": "email", "message": "Enter a valid email address."}]


def test_openapi_lists_envelope_errors(client):
    paths = client.get("/api/openapi.json").json()["paths"]

    def ref(path, method, status):
        return paths[path][method]["responses"][status]["content"]["application/json"]["schema"]["$ref"]

    for status in ("401", "422", "429", "503"):
        assert ref("/api/v1/login", "post", status).endswith("/ErrorEnvelope")
    assert ref("/api/v1/me", "get", "401").endswith("/ErrorEnvelope")

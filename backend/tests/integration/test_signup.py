# Integration tests: POST /api/v1/signup creates a Business, a User, and an Owner membership
# in one transaction (FR-7, AD-4, AD-15). Emails are unique per test, so tests never collide.
import uuid

import sqlalchemy.orm
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.main import app
from app.modules.accounts import service as accounts_service
from app.modules.accounts.models import Membership, User
from app.modules.accounts.repository import UserRepository
from app.modules.business.models import Business

GOOD_PASSWORD = "correct horse battery"


def email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


def counts() -> tuple[int, int, int]:
    # How many businesses, users, and memberships exist right now.
    with Session(get_engine()) as s:
        return tuple(s.scalar(select(func.count()).select_from(m)) for m in (Business, User, Membership))


def sign_up(client, **overrides):
    body = {"business_name": "Sharma Plumbing", "email": email(), "password": GOOD_PASSWORD} | overrides
    return client.post("/api/v1/signup", json=body)


def test_signup_creates_business_user_and_owner_membership(client):
    address = email()
    response = sign_up(client, email=address.upper())
    assert response.status_code == 201
    body = response.json()
    assert body["business_name"] == "Sharma Plumbing"

    with Session(get_engine()) as s:
        business = s.get(Business, uuid.UUID(body["business_id"]))
        assert business.name == "Sharma Plumbing"
        user = s.scalars(select(User).where(User.email == address)).one()  # stored lowercased
        membership = s.scalars(select(Membership).where(Membership.user_id == user.id)).one()
        assert membership.business_id == business.id
        assert set(membership.roles) == {"owner", "technician"}
        assert membership.is_active is True


def test_password_is_stored_only_as_argon2id_hash(client):
    address = email()
    assert sign_up(client, email=address).status_code == 201
    with Session(get_engine()) as s:
        password_hash = s.scalars(select(User.password_hash).where(User.email == address)).one()
    assert password_hash.startswith("$argon2id$")
    assert GOOD_PASSWORD not in password_hash


def test_taken_email_returns_409_and_creates_nothing(client):
    before = counts()
    address = email()
    assert sign_up(client, email=address).status_code == 201
    response = sign_up(client, email=f"  {address.upper()} ")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "email_taken"
    assert error["fields"][0]["field"] == "email"
    assert counts() == tuple(n + 1 for n in before)


def test_email_race_returns_409(client, monkeypatch):
    address = email()
    assert sign_up(client, email=address).status_code == 201
    before = counts()
    # Pretend the lookup missed it, as when two sign-ups arrive at the same moment.
    monkeypatch.setattr(UserRepository, "email_exists", lambda self, email: False)
    response = sign_up(client, email=address)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"
    assert counts() == before


def test_invalid_input_lists_each_field(client):
    response = client.post("/api/v1/signup", json={"business_name": "   ", "email": "nope", "password": "short"})
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [
        {"field": "business_name", "message": "Enter your business name."},
        {"field": "email", "message": "Enter a valid email address."},
        {"field": "password", "message": "Use at least 12 characters."},
    ]


def test_too_long_input_is_refused(client):
    response = client.post("/api/v1/signup", json={"business_name": "x" * 101, "email": email(), "password": "p" * 129})
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [
        {"field": "business_name", "message": "Use at most 100 characters."},
        {"field": "password", "message": "Use at most 128 characters."},
    ]


def test_twelve_hindi_characters_are_a_valid_password(client):
    assert sign_up(client, password="क" * 12).status_code == 201


def test_password_spaces_are_kept(client):
    address = email()
    password = "  spaces at both ends  "
    assert sign_up(client, email=address, password=password).status_code == 201
    with Session(get_engine()) as s:
        password_hash = s.scalars(select(User.password_hash).where(User.email == address)).one()
    hasher = PasswordHash((Argon2Hasher(),))
    assert hasher.verify(password, password_hash)
    assert not hasher.verify(password.strip(), password_hash)


def test_crash_mid_signup_leaves_nothing(client, monkeypatch):
    before = counts()

    def crash(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(accounts_service, "create_owner", crash)
    response = sign_up(TestClient(app, raise_server_exceptions=False))
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert counts() == before


def test_failed_commit_gives_500_and_saves_nothing(client, monkeypatch):
    before = counts()

    def fail(self, *args, **kwargs):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(sqlalchemy.orm.SessionTransaction, "commit", fail)
    response = sign_up(TestClient(app, raise_server_exceptions=False))
    monkeypatch.undo()
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert counts() == before


def test_openapi_lists_signup_with_envelope_errors(client):
    schema = client.get("/api/openapi.json").json()
    responses = schema["paths"]["/api/v1/signup"]["post"]["responses"]
    assert {"201", "409", "422"} <= set(responses)

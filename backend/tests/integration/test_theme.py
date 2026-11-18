# Database rules for the users.theme column (story 2.6). Every User starts on "system",
# and the database itself refuses any value that is not system, light or dark.
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tests.integration.conftest import GOOD_PASSWORD

from app.core.db import get_engine

pytestmark = pytest.mark.isolation


def owner_user_id(business_id):
    """Find the Owner's user id through their membership in this Business."""
    with get_engine().begin() as conn:
        sql = text("SELECT user_id FROM memberships WHERE business_id = :id")
        return conn.execute(sql, {"id": business_id}).scalar_one()


def test_new_user_theme_is_system(sign_up_owner):
    # Behaviour: a brand new User starts on the "system" theme.
    _client, business_id = sign_up_owner()
    user_id = owner_user_id(business_id)
    with get_engine().begin() as conn:
        theme = conn.execute(text("SELECT theme FROM users WHERE id = :id"), {"id": user_id}).scalar_one()
    assert theme == "system"


def test_database_refuses_unknown_theme(sign_up_owner):
    # Behaviour: the database itself refuses a theme that is not system, light or dark.
    _client, business_id = sign_up_owner()
    user_id = owner_user_id(business_id)
    with pytest.raises(IntegrityError), get_engine().begin() as conn:
        conn.execute(text("UPDATE users SET theme = 'blue' WHERE id = :id"), {"id": user_id})


def test_me_starts_with_system(sign_up_owner):
    # Behaviour: GET /me says the theme is "system" for a brand new User.
    owner, _business_id = sign_up_owner()
    assert owner.get("/api/v1/me").json()["theme"] == "system"


def test_saved_theme_comes_back_on_another_device(make_client):
    # Behaviour: a theme saved on one device is returned by log-in and /me on another device.
    email = f"{uuid.uuid4().hex}@example.com"
    first = make_client()
    body = {"business_name": "Test Shop", "email": email, "password": GOOD_PASSWORD}
    assert first.post("/api/v1/signup", json=body).status_code == 201
    assert first.put("/api/v1/me/theme", json={"theme": "dark"}).status_code == 204

    other_device = make_client()
    login = other_device.post("/api/v1/login", json={"email": email, "password": GOOD_PASSWORD})
    assert login.status_code == 200
    assert login.json()["theme"] == "dark"
    assert other_device.get("/api/v1/me").json()["theme"] == "dark"


def test_unknown_theme_is_422_and_nothing_changes(sign_up_owner):
    # Behaviour: a theme that is not system, light or dark (or a missing one) is refused and nothing is saved.
    owner, _business_id = sign_up_owner()
    assert owner.put("/api/v1/me/theme", json={"theme": "blue"}).status_code == 422
    assert owner.put("/api/v1/me/theme", json={}).status_code == 422
    assert owner.get("/api/v1/me").json()["theme"] == "system"


def test_set_theme_needs_login(client):
    # Behaviour: saving a theme without being logged in is refused with 401.
    assert client.put("/api/v1/me/theme", json={"theme": "dark"}).status_code == 401


def test_light_replaces_dark(sign_up_owner):
    # Behaviour: a later choice replaces an earlier one; "light" is saved and read back.
    owner, _ = sign_up_owner()
    assert owner.put("/api/v1/me/theme", json={"theme": "dark"}).status_code == 204
    assert owner.put("/api/v1/me/theme", json={"theme": "light"}).status_code == 204
    assert owner.get("/api/v1/me").json()["theme"] == "light"

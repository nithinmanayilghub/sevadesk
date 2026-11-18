# Integration tests: an Owner creates an invite link (story 2.5, FR-9).
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.conftest import set_owner_roles

from app.core.db import get_engine
from app.modules.accounts.models import Invite

FORBIDDEN_BODY = {"error": {"code": "forbidden", "message": "You don't have access to this."}}


def invites_of(business_id: uuid.UUID) -> list[Invite]:
    """Every invite row of this Business (a direct database read, outside the app's rules)."""
    with Session(get_engine()) as session:
        return list(session.scalars(select(Invite).where(Invite.business_id == business_id)))


def field_errors(response) -> list[dict]:
    return response.json()["error"]["fields"]


def test_owner_gets_a_token_once_and_db_keeps_only_its_hash(sign_up_owner):
    # Behaviour: the raw token is shown once; the database keeps only its hash.
    owner, business_id = sign_up_owner()
    response = owner.post("/api/v1/team/invites", json={"email": "  New@Shop.IN ", "roles": ["technician"]})
    assert response.status_code == 201, response.text
    body = response.json()
    token = body["token"]
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert abs(expires_at - (datetime.now(UTC) + timedelta(days=7))) < timedelta(minutes=1)

    [invite] = invites_of(business_id)
    assert invite.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in (invite.token_hash, invite.email)
    assert invite.email == "new@shop.in"
    assert invite.roles == ["technician"]
    assert invite.used_at is None


@pytest.mark.parametrize("roles", [["staff"], ["technician"]])
def test_forbidden_roles_cannot_create_an_invite(sign_up_owner, roles):
    # Behaviour: only the Owner may invite. A VALID body, so the 403 is the Role check
    # (FastAPI checks the body first; a bad body would give 422).
    owner, business_id = sign_up_owner()
    set_owner_roles(business_id, roles)
    response = owner.post("/api/v1/team/invites", json={"email": "new@shop.in", "roles": ["staff"]})
    assert (response.status_code, response.json()) == (403, FORBIDDEN_BODY)
    assert invites_of(business_id) == []


def test_owner_role_cannot_be_invited(sign_up_owner):
    owner, _ = sign_up_owner()
    response = owner.post("/api/v1/team/invites", json={"email": "new@shop.in", "roles": ["owner"]})
    assert response.status_code == 422
    assert field_errors(response) == [{"field": "roles", "message": "Choose Staff, Technician, or both."}]


def test_empty_roles_are_refused(sign_up_owner):
    owner, _ = sign_up_owner()
    response = owner.post("/api/v1/team/invites", json={"email": "new@shop.in", "roles": []})
    assert response.status_code == 422
    assert field_errors(response) == [{"field": "roles", "message": "Choose at least one Role."}]


def test_bad_email_is_refused(sign_up_owner):
    owner, _ = sign_up_owner()
    response = owner.post("/api/v1/team/invites", json={"email": "not-an-email", "roles": ["staff"]})
    assert response.status_code == 422
    assert field_errors(response) == [{"field": "email", "message": "Enter a valid email address."}]

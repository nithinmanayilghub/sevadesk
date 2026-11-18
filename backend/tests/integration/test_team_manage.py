# Integration tests: Settings → Team (story 2.5, FR-7, FR-9, FR-10, AD-4, AD-5).
# The Owner lists members, changes Roles, and deactivates (never deletes) a member.
# Ids come from invite_member and GET /team, never from membership_of (it assumes one member).
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.integration.conftest import GOOD_PASSWORD

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.modules.accounts import service as accounts_service
from app.modules.accounts.models import Membership, UserSession

FORBIDDEN_BODY = {"error": {"code": "forbidden", "message": "You don't have access to this."}}


def team(client) -> dict:
    response = client.get("/api/v1/team")
    assert response.status_code == 200, response.text
    return response.json()


def own_membership_id(owner) -> uuid.UUID:
    [me] = [m for m in team(owner)["members"] if m["is_you"]]
    return uuid.UUID(me["membership_id"])


def patch(client, membership_id: uuid.UUID, body: dict):
    return client.patch(f"/api/v1/team/members/{membership_id}", json=body)


def membership_row(membership_id: uuid.UUID) -> Membership:
    with Session(get_engine()) as session:
        return session.get(Membership, membership_id)


def log_in(client, email: str):
    return client.post("/api/v1/login", json={"email": email, "password": GOOD_PASSWORD})


def test_solo_owner_sees_just_you(sign_up_owner):
    # Behaviour: an Owner alone is the only active Technician, so the page says "Just you for now".
    owner, _ = sign_up_owner()
    body = team(owner)
    assert body["just_you"] is True
    [me] = body["members"]
    assert me["is_you"] is True
    assert me["roles"] == ["owner", "technician"]
    assert me["is_active"] is True


def test_a_second_technician_ends_just_you(sign_up_owner, invite_member):
    owner, _ = sign_up_owner()
    member = invite_member(owner, ["technician"])
    body = team(owner)
    assert body["just_you"] is False
    assert [m["email"] for m in body["members"]][1] == member.email  # oldest first


def test_owner_turns_off_own_technician_role(sign_up_owner):
    # Behaviour (FR-7): without the Technician Role, the Owner no longer counts as an active Technician.
    owner, business_id = sign_up_owner()
    my_id = own_membership_id(owner)
    response = patch(owner, my_id, {"roles": ["owner"]})
    assert response.status_code == 200, response.text
    assert response.json()["just_you"] is False
    with Session(get_engine()) as session, tenant_scope(business_id):
        assert my_id not in accounts_service.active_technician_ids(session)


def test_owner_changes_a_members_roles_and_it_applies_at_once(sign_up_owner, invite_member):
    # Behaviour: Roles are read on every request, so the member's next request has the new Roles.
    owner, _ = sign_up_owner()
    member = invite_member(owner, ["staff"])
    assert patch(owner, member.membership_id, {"roles": ["technician"]}).status_code == 200
    assert member.client.get("/api/v1/me").json()["roles"] == ["technician"]


def test_deactivated_member_is_logged_out_everywhere(sign_up_owner, invite_member, make_client):
    # Behaviour: deactivation deletes every session at once; the membership row stays (AD-4, AD-5).
    owner, _ = sign_up_owner()
    member = invite_member(owner, ["staff"])
    second_phone = make_client()
    assert log_in(second_phone, member.email).status_code == 200

    response = patch(owner, member.membership_id, {"is_active": False})
    assert response.status_code == 200, response.text
    assert member.client.get("/api/v1/me").status_code == 401
    assert second_phone.get("/api/v1/me").status_code == 401
    assert log_in(make_client(), member.email).status_code == 401

    row = membership_row(member.membership_id)
    assert row is not None and row.is_active is False
    with Session(get_engine()) as session:
        sessions = session.scalar(
            select(func.count()).select_from(UserSession).where(UserSession.user_id == row.user_id)
        )
    assert sessions == 0


def test_reactivated_member_can_log_in_again(sign_up_owner, invite_member, make_client):
    owner, _ = sign_up_owner()
    member = invite_member(owner, ["staff"])
    assert patch(owner, member.membership_id, {"is_active": False}).status_code == 200
    assert patch(owner, member.membership_id, {"is_active": True}).status_code == 200
    assert log_in(make_client(), member.email).status_code == 200


def test_reactivation_does_not_bring_old_sessions_back(sign_up_owner, invite_member):
    # Behaviour: after reactivation, the old phone's session stays dead (401): delete_for_user ran.
    owner, _ = sign_up_owner()
    member = invite_member(owner, ["staff"])
    assert member.client.get("/api/v1/me").status_code == 200  # logged in before

    assert patch(owner, member.membership_id, {"is_active": False}).status_code == 200
    assert patch(owner, member.membership_id, {"is_active": True}).status_code == 200

    assert member.client.get("/api/v1/me").status_code == 401  # the old phone


@pytest.mark.parametrize(
    ("target", "body", "field", "message"),
    [
        ("self", {"roles": ["technician"]}, "roles", "The Owner Role can't be changed."),
        ("member", {"roles": ["owner", "staff"]}, "roles", "The Owner Role can't be changed."),
        ("self", {"is_active": False}, "is_active", "You can't deactivate yourself."),
    ],
)
def test_owner_rules_cannot_be_broken(sign_up_owner, invite_member, target, body, field, message):
    # Behaviour: the Owner cannot lose the Owner Role, give it away, or lock themself out.
    owner, _ = sign_up_owner()
    member = invite_member(owner, ["staff"])
    membership_id = own_membership_id(owner) if target == "self" else member.membership_id
    before = membership_row(membership_id)

    response = patch(owner, membership_id, body)
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [{"field": field, "message": message}]
    after = membership_row(membership_id)
    assert (after.roles, after.is_active) == (before.roles, before.is_active)


def test_empty_change_is_refused(sign_up_owner):
    owner, _ = sign_up_owner()
    response = patch(owner, own_membership_id(owner), {})
    assert response.status_code == 422
    # A whole-body rule has no field name, so the envelope carries only the general message.
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("roles", [["staff"], ["technician"]])
def test_forbidden_roles_cannot_see_or_change_the_team(sign_up_owner, invite_member, roles):
    # Behaviour: only the Owner manages the team (FR-10). A VALID body, so the 403 is the Role check.
    owner, _ = sign_up_owner()
    owner_id = own_membership_id(owner)
    member = invite_member(owner, roles)
    response = member.client.get("/api/v1/team")
    assert (response.status_code, response.json()) == (403, FORBIDDEN_BODY)
    response = patch(member.client, owner_id, {"roles": ["owner"]})
    assert (response.status_code, response.json()) == (403, FORBIDDEN_BODY)

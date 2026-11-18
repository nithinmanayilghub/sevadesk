# Integration tests: open and accept an invite link (story 2.5, FR-9, AD-3, AD-5).
# The invited person has no session, so the backend finds the invite by its token in an
# audited system_scope, then makes the User inside the invite's own Business.
import secrets
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session
from tests.integration.conftest import GOOD_PASSWORD

from app.core.db import get_engine
from app.core.session_cookie import SESSION_COOKIE
from app.modules.accounts.models import Invite, Membership, User
from app.modules.accounts.schemas import Role
from app.modules.accounts.service import hash_token, permissions_for

INVALID_BODY = {"error": {"code": "invite_invalid", "message": "This invite is no longer valid."}}


def new_invite(owner, roles: list[str], email: str | None = None) -> tuple[str, str]:
    """The Owner makes an invite. Returns (raw token, invited email)."""
    email = email or f"{uuid.uuid4().hex}@example.com"
    response = owner.post("/api/v1/team/invites", json={"email": email, "roles": roles})
    assert response.status_code == 201, response.text
    return response.json()["token"], email


def accept(client, token: str, password: str = GOOD_PASSWORD):
    return client.post("/api/v1/invites/accept", json={"token": token, "password": password})


def invite_row(token: str) -> Invite:
    with Session(get_engine()) as session:
        return session.scalars(select(Invite).where(Invite.token_hash == hash_token(token))).one()


def users_with_email(email: str) -> int:
    with Session(get_engine()) as session:
        return session.scalar(select(func.count()).select_from(User).where(User.email == email))


def test_preview_shows_the_invited_email(sign_up_owner, client):
    owner, _ = sign_up_owner()
    token, email = new_invite(owner, ["staff"])
    response = client.post("/api/v1/invites/preview", json={"token": token})
    assert (response.status_code, response.json()) == (200, {"email": email})


def test_accept_makes_a_member_with_the_invited_roles_and_logs_in(sign_up_owner, client):
    # Behaviour: accept makes the User and membership in the invite's Business, and logs in.
    owner, business_id = sign_up_owner()
    token, email = new_invite(owner, ["staff", "technician"])
    response = accept(client, token)
    assert response.status_code == 200, response.text
    roles = {Role.STAFF, Role.TECHNICIAN}
    assert response.json() == {"roles": ["staff", "technician"], "permissions": permissions_for(roles)}
    assert client.get("/api/v1/me").status_code == 200  # the cookie works at once
    with Session(get_engine()) as session:
        query = select(Membership).join(User, User.id == Membership.user_id).where(User.email == email)
        membership = session.scalars(query).one()
    assert membership.business_id == business_id
    assert invite_row(token).used_at is not None


def test_used_invite_is_no_longer_valid(sign_up_owner, make_client):
    # Behaviour: an invite works once.
    owner, _ = sign_up_owner()
    token, email = new_invite(owner, ["staff"])
    assert accept(make_client(), token).status_code == 200
    second = make_client()
    for response in (second.post("/api/v1/invites/preview", json={"token": token}), accept(second, token)):
        assert (response.status_code, response.json()) == (404, INVALID_BODY)
    assert users_with_email(email) == 1


def test_expired_invite_is_no_longer_valid(sign_up_owner, client):
    # Behaviour: after 7 days the link stops working, and nothing is created.
    owner, _ = sign_up_owner()
    token, email = new_invite(owner, ["staff"])
    with Session(get_engine()) as session, session.begin():
        session.execute(
            update(Invite)
            .where(Invite.token_hash == hash_token(token))
            .values(expires_at=func.now() - text("interval '1 second'"))
        )
    for response in (client.post("/api/v1/invites/preview", json={"token": token}), accept(client, token)):
        assert (response.status_code, response.json()) == (404, INVALID_BODY)
    assert users_with_email(email) == 0


def test_unknown_token_is_no_longer_valid(client):
    token = secrets.token_urlsafe(32)
    for response in (client.post("/api/v1/invites/preview", json={"token": token}), accept(client, token)):
        assert (response.status_code, response.json()) == (404, INVALID_BODY)


def test_too_long_token_is_a_field_error(client):
    response = client.post("/api/v1/invites/preview", json={"token": "a" * 65})
    assert response.status_code == 422
    assert response.json()["error"]["fields"][0]["field"] == "token"


def test_email_that_already_has_an_account_gets_409(sign_up_owner, make_client, client):
    # Behaviour: one email = one account. The invite stays unused, and nothing is created.
    owner, business_id = sign_up_owner()
    taken_email = f"{uuid.uuid4().hex}@example.com"
    signup = {"business_name": "Other Shop", "email": taken_email, "password": GOOD_PASSWORD}
    assert make_client().post("/api/v1/signup", json=signup).status_code == 201
    token, _ = new_invite(owner, ["staff"], email=taken_email)
    response = accept(client, token)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"
    assert invite_row(token).used_at is None
    with Session(get_engine()) as session:
        count = session.scalar(
            select(func.count()).select_from(Membership).where(Membership.business_id == business_id)
        )
    assert count == 1  # still only the Owner


def test_second_accept_waits_for_the_lock_and_then_fails(sign_up_owner, client):
    # Behaviour: the row lock makes a second accept WAIT; when it may go on, it sees the
    # invite is used and fails. (Without the lock it would not wait at all.)
    owner, _ = sign_up_owner()
    token, email = new_invite(owner, ["staff"])
    with get_engine().connect() as conn, ThreadPoolExecutor(max_workers=1) as pool:
        tx = conn.begin()
        # Play "the first accept": hold the lock on this invite row.
        conn.execute(text("SELECT id FROM invites WHERE token_hash = :h FOR UPDATE"), {"h": hash_token(token)})
        future = pool.submit(accept, client, token)
        time.sleep(0.5)
        assert not future.done(), "accept did not wait for the row lock"
        # The first accept finishes: the invite is now used.
        conn.execute(text("UPDATE invites SET used_at = now() WHERE token_hash = :h"), {"h": hash_token(token)})
        tx.commit()
        response = future.result(timeout=30)
    assert (response.status_code, response.json()) == (404, INVALID_BODY)
    assert users_with_email(email) == 0


def test_short_password_is_a_field_error(sign_up_owner, client):
    owner, _ = sign_up_owner()
    token, _ = new_invite(owner, ["staff"])
    response = accept(client, token, password="short")
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [{"field": "password", "message": "Use at least 12 characters."}]
    assert invite_row(token).used_at is None


def test_accept_on_a_shared_phone_ends_the_previous_session(sign_up_owner, make_client):
    # Behaviour: the Owner hands their phone to the new member, who accepts there. The Owner's
    # old session must stop working, so the next person cannot act as the Owner (D11).
    owner, _ = sign_up_owner()
    token, _ = new_invite(owner, ["staff"])
    owners_token = owner.cookies[SESSION_COOKIE]
    assert accept(owner, token).status_code == 200  # same browser = same phone
    old = make_client().get("/api/v1/me", headers={"Cookie": f"{SESSION_COOKIE}={owners_token}"})
    assert old.status_code == 401


def test_failed_accept_keeps_the_current_session(sign_up_owner):
    # Behaviour: a dead link changes nothing; the rollback also undoes the "end old session" step.
    owner, _ = sign_up_owner()
    assert accept(owner, secrets.token_urlsafe(32)).status_code == 404
    assert owner.get("/api/v1/me").status_code == 200

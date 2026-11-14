# Integration tests for server-side sessions in accounts (story 2.2, AD-5).
# A session is a row in "sessions". The browser holds a random token; the DB holds only
# its SHA-256 hash, so a leaked DB backup gives no working cookies.
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.modules.accounts import service as accounts_service
from app.modules.accounts.models import Membership, UserSession
from app.modules.accounts.schemas import Role
from app.modules.business.repository import BusinessRepository

pytestmark = pytest.mark.usefixtures("migrated_db")


def make_owner(s: Session) -> tuple[uuid.UUID, uuid.UUID]:
    # Built directly, not with business.service.sign_up (Task 4 changes sign_up).
    business = BusinessRepository(s).add("Test Shop")
    with tenant_scope(business.id):
        owner = accounts_service.create_owner(s, f"{uuid.uuid4().hex}@example.com", "correct horse battery")
    return owner.user_id, business.id


def owner_with_session() -> tuple[str, uuid.UUID, uuid.UUID]:
    """Commit a new Owner and a session; return (token, user_id, business_id)."""
    with Session(get_engine()) as s, s.begin():
        user_id, business_id = make_owner(s)
        token = accounts_service.start_session(s, user_id)
    return token, user_id, business_id


def set_last_seen(token: str, when: datetime) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with Session(get_engine()) as s, s.begin():
        s.execute(update(UserSession).where(UserSession.token_hash == token_hash).values(last_seen_at=when))


def last_seen(token: str) -> datetime:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with Session(get_engine()) as s:
        return s.scalars(select(UserSession.last_seen_at).where(UserSession.token_hash == token_hash)).one()


def resolve(token: str | None):
    with Session(get_engine()) as s, s.begin():
        return accounts_service.resolve_session(s, token)


def test_start_session_stores_only_the_token_hash():
    token, user_id, _ = owner_with_session()
    with Session(get_engine()) as s:
        row = s.scalars(select(UserSession).where(UserSession.user_id == user_id)).one()
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in row.token_hash


def test_resolve_session_returns_the_actor():
    token, user_id, business_id = owner_with_session()
    actor = resolve(token)
    assert actor.user_id == user_id
    assert actor.business_id == business_id
    assert actor.roles == {Role.OWNER, Role.TECHNICIAN}


def test_unknown_or_missing_token_is_not_authenticated():
    for token in ("nope", None):
        with pytest.raises(accounts_service.NotAuthenticated):
            resolve(token)


def test_idle_session_is_refused():
    token, _, _ = owner_with_session()
    set_last_seen(token, datetime.now(UTC) - accounts_service.SESSION_IDLE_TIMEOUT - timedelta(minutes=1))
    with pytest.raises(accounts_service.NotAuthenticated):
        resolve(token)


def test_touch_only_after_five_minutes():
    token, _, _ = owner_with_session()
    one_minute_ago = datetime.now(UTC) - timedelta(minutes=1)
    set_last_seen(token, one_minute_ago)
    resolve(token)
    assert last_seen(token) == one_minute_ago  # fresh enough: no write

    set_last_seen(token, datetime.now(UTC) - timedelta(minutes=6))
    resolve(token)
    assert datetime.now(UTC) - last_seen(token) < timedelta(seconds=30)  # moved to about now


def test_inactive_membership_is_refused():
    token, user_id, _ = owner_with_session()
    with Session(get_engine()) as s, s.begin():
        s.execute(update(Membership).where(Membership.user_id == user_id).values(is_active=False))
    with pytest.raises(accounts_service.NotAuthenticated):
        resolve(token)


def test_end_session_deletes_the_row():
    token, _, _ = owner_with_session()
    with Session(get_engine()) as s, s.begin():
        accounts_service.end_session(s, token)
        accounts_service.end_session(s, None)  # nothing to end: no error
        accounts_service.end_session(s, "nope")  # unknown token: no error
    with pytest.raises(accounts_service.NotAuthenticated):
        resolve(token)

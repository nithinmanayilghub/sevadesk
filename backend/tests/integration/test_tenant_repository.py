# Integration tests: the new tables, and the tenant-scoped base repository (AD-3, AD-4).
# Each test uses one DB session and never commits, so its rows vanish at the end.
import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.core.tenancy import SystemScopeRequired, TenantContextMissing, system_scope, tenant_scope
from app.modules.accounts.models import Membership, UserSession
from app.modules.accounts.repository import MembershipRepository, UserRepository
from app.modules.business.repository import BusinessRepository


def unique_email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


@pytest.fixture
def session(client):
    # `client` migrates the test database first.
    with Session(get_engine()) as s:
        yield s
        s.rollback()


def make_membership(session: Session, business_id: uuid.UUID, roles: list[str] | None = None) -> Membership:
    user = UserRepository(session).add(unique_email(), "not-a-real-hash")
    with tenant_scope(business_id):
        return MembershipRepository(session).add(
            Membership(user_id=user.id, roles=["owner"] if roles is None else roles)
        )


def test_migration_creates_the_four_tables(client):
    tables = set(inspect(get_engine()).get_table_names())
    assert {"businesses", "users", "sessions", "memberships"} <= tables


def test_new_rows_get_uuidv7_ids(session):
    business = BusinessRepository(session).add("Sharma Plumbing")
    user = UserRepository(session).add(unique_email(), "not-a-real-hash")
    with tenant_scope(business.id):
        membership = MembershipRepository(session).add(Membership(user_id=user.id, roles=["owner"]))
    user_session = UserSession(user_id=user.id, token_hash=uuid.uuid4().hex)
    session.add(user_session)
    session.flush()
    for row in (business, user, membership, user_session):
        assert row.id.version == 7


def test_membership_get_hides_other_business(session):
    business_a = BusinessRepository(session).add("A")
    business_b = BusinessRepository(session).add("B")
    membership = make_membership(session, business_a.id)

    with tenant_scope(business_b.id):
        assert MembershipRepository(session).get(membership.id) is None
    with tenant_scope(business_a.id):
        assert MembershipRepository(session).get(membership.id) is membership


def test_add_without_tenant_raises(session):
    user = UserRepository(session).add(unique_email(), "not-a-real-hash")
    with pytest.raises(TenantContextMissing):
        MembershipRepository(session).add(Membership(user_id=user.id, roles=["owner"]))


def test_add_overwrites_business_id(session):
    business_a = BusinessRepository(session).add("A")
    business_b = BusinessRepository(session).add("B")
    user = UserRepository(session).add(unique_email(), "not-a-real-hash")
    with tenant_scope(business_a.id):
        row = MembershipRepository(session).add(Membership(user_id=user.id, roles=["owner"], business_id=business_b.id))
    assert row.business_id == business_a.id


@pytest.mark.parametrize("roles", [[], ["admin"]])
def test_database_refuses_bad_roles(session, roles):
    business = BusinessRepository(session).add("A")
    with pytest.raises(IntegrityError):
        make_membership(session, business.id, roles=roles)


def test_one_business_per_user(session):
    business_a = BusinessRepository(session).add("A")
    business_b = BusinessRepository(session).add("B")
    membership = make_membership(session, business_a.id)
    with tenant_scope(business_b.id), pytest.raises(IntegrityError):
        MembershipRepository(session).add(Membership(user_id=membership.user_id, roles=["staff"]))


def test_email_exists_needs_system_scope(session):
    email = unique_email()
    UserRepository(session).add(email, "not-a-real-hash")
    with pytest.raises(SystemScopeRequired):
        UserRepository(session).email_exists(email)
    with system_scope("signup"):
        assert UserRepository(session).email_exists(email) is True
        assert UserRepository(session).email_exists(unique_email()) is False

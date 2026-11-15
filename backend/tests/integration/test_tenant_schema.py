# Database guards for tenant tables (story 2.3, AD-3).
#
# Rule 1: every table is either global (listed below) or a tenant table
#         (it has business_id -> businesses.id).
# Rule 2: every tenant table has UNIQUE (business_id, id), so others can link to it safely.
# Rule 3: a link to a tenant table uses BOTH columns: (business_id, x_id) -> (business_id, id).
#         Then the database itself refuses a row in Business A that points at Business B.
import uuid

import pytest
from sqlalchemy import Column, ForeignKeyConstraint, MetaData, Table, Uuid, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.modules.accounts.models import Membership
from app.modules.accounts.repository import MembershipRepository, UserRepository
from app.modules.business.repository import BusinessRepository

pytestmark = pytest.mark.isolation

GLOBAL_TABLES = {"alembic_version", "app_meta", "businesses", "users", "sessions"}


def _is_tenant_table(inspector, table: str) -> bool:
    return any(
        fk["referred_table"] == "businesses" and fk["constrained_columns"] == ["business_id"]
        for fk in inspector.get_foreign_keys(table)
    )


def tenant_schema_violations(inspector) -> list[str]:
    """Every break of the three rules above, as readable sentences. Empty means all good."""
    tables = inspector.get_table_names(schema="public")
    tenant_tables = {t for t in tables if t not in GLOBAL_TABLES and _is_tenant_table(inspector, t)}
    violations = []
    for table in tables:
        if table not in GLOBAL_TABLES and table not in tenant_tables:
            violations.append(f"{table}: neither global nor tenant (no business_id -> businesses.id)")
    for table in tenant_tables:
        uniques = [set(u["column_names"]) for u in inspector.get_unique_constraints(table)]
        if {"business_id", "id"} not in uniques:
            violations.append(f"{table}: missing UNIQUE (business_id, id)")
    for table in tables:
        for fk in inspector.get_foreign_keys(table):
            if fk["referred_table"] not in tenant_tables:
                continue
            pairs = set(zip(fk["constrained_columns"], fk["referred_columns"], strict=True))
            if ("business_id", "business_id") not in pairs or set(fk["referred_columns"]) != {"business_id", "id"}:
                violations.append(f"{table}: link to {fk['referred_table']} is not composite")
    return violations


def test_real_schema_follows_the_tenant_rules(migrated_db):
    with get_engine().connect() as conn:
        assert tenant_schema_violations(inspect(conn)) == []


def test_rules_catch_a_bad_tenant_table(migrated_db):
    with get_engine().connect() as conn, conn.begin() as tx:
        # A real table in "public" (a TEMP table lives elsewhere, and the rules read only public).
        conn.execute(
            text(
                "CREATE TABLE bad_notes (id uuid PRIMARY KEY, "
                "business_id uuid REFERENCES businesses(id), "
                "membership_id uuid REFERENCES memberships(id))"
            )
        )
        violations = tenant_schema_violations(inspect(conn))
        tx.rollback()  # the table is gone again
    assert any("bad_notes" in v and "UNIQUE" in v for v in violations)
    assert any("bad_notes" in v and "not composite" in v for v in violations)


def _business_with_membership(session: Session, name: str) -> tuple[uuid.UUID, uuid.UUID]:
    business = BusinessRepository(session).add(name)
    user = UserRepository(session).add(f"{uuid.uuid4().hex}@example.com", "not-a-real-hash")
    with tenant_scope(business.id):
        membership = MembershipRepository(session).add(Membership(user_id=user.id, roles=["owner"]))
    return business.id, membership.id


def test_database_refuses_a_link_to_another_business(migrated_db):
    with get_engine().connect() as conn, conn.begin() as tx:
        # Read the real memberships table, so the two-column link below can point at it.
        metadata = MetaData()
        Table("memberships", metadata, autoload_with=conn)
        notes = Table(
            "good_notes",
            metadata,
            Column("id", Uuid, primary_key=True),
            Column("business_id", Uuid),
            Column("membership_id", Uuid),
            ForeignKeyConstraint(["business_id", "membership_id"], ["memberships.business_id", "memberships.id"]),
        )
        notes.create(conn)
        session = Session(bind=conn)  # joins this transaction, so everything is rolled back
        a_id, a_membership = _business_with_membership(session, "A")
        _, b_membership = _business_with_membership(session, "B")

        # Own Business: allowed.
        conn.execute(notes.insert().values(id=uuid.uuid7(), business_id=a_id, membership_id=a_membership))
        # Business A pointing at Business B's membership: the database says no.
        with pytest.raises(IntegrityError), conn.begin_nested():
            conn.execute(notes.insert().values(id=uuid.uuid7(), business_id=a_id, membership_id=b_membership))
        session.close()
        tx.rollback()

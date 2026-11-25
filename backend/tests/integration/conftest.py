# Integration test fixtures: a real Postgres in Docker, migrated, plus an API client.
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.valkey import ValkeyContainer

from app.core.db import get_engine
from app.core.redis_client import get_redis
from app.core.settings import get_settings
from app.core.telemetry import add_span_exporter, flush_telemetry
from app.main import app
from app.modules.accounts.models import Membership, User

# alembic.ini lives in backend/, two folders above this file's folder.
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
GOOD_PASSWORD = "correct horse battery"


@pytest.fixture(scope="session")
def pg():
    # One Postgres container for the whole test run (starting it is slow).
    with PostgresContainer("postgres:18", driver="psycopg") as container:
        yield container


@pytest.fixture(scope="session")
def valkey():
    # One Valkey container for the whole test run.
    with ValkeyContainer("valkey/valkey:9.0") as container:
        yield container


@pytest.fixture(scope="session")
def redis_url(valkey) -> str:
    # redis-py does not accept the valkey:// scheme, so build redis:// ourselves.
    return f"redis://{valkey.get_host()}:{valkey.get_exposed_port()}/0"


class SpanRecorder:
    """Keeps every finished span in memory, so tests can check the trace."""

    def __init__(self):
        self.memory = InMemorySpanExporter()
        # The same door every real exporter uses, so test spans are masked too.
        add_span_exporter(self.memory)

    def clear(self) -> None:
        # Flush first: spans from earlier work (e.g. migrations) may still wait in the batch.
        flush_telemetry()
        self.memory.clear()

    def finished(self) -> list:
        flush_telemetry()  # the batch processor sends spans later; push them out now
        return list(self.memory.get_finished_spans())


@pytest.fixture(scope="session")
def spans() -> SpanRecorder:
    return SpanRecorder()


@pytest.fixture
def migrated_db(pg, redis_url, monkeypatch):
    """A migrated Postgres and a Valkey, for tests that use the DB without the API."""
    monkeypatch.setenv("DATABASE_URL", pg.get_connection_url())
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("APP_VERSION", "test-1")
    # Settings and engine are cached, so clear them to pick up the env vars above.
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_redis.cache_clear()
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    # Empty Valkey: the log-in counters (per IP) would otherwise pile up across tests.
    get_redis().flushdb()
    yield
    # Close pooled connections so nothing is left open after the test.
    get_engine().dispose()


def _make_client(**kwargs) -> TestClient:
    # https: the browser sends a Secure cookie back only over https, and so does the test client.
    # Origin: the same site, as a browser sends on POST (the CSRF guard checks it, AD-5).
    return TestClient(app, base_url="https://testserver", headers={"Origin": "https://testserver"}, **kwargs)


@pytest.fixture
def make_client(migrated_db):
    """Build extra clients, e.g. make_client(raise_server_exceptions=False) or a second browser."""
    return _make_client


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.fixture
def sign_up_owner(make_client):
    """Sign up a new Business; returns (logged-in client, business_id). Call it once per Owner."""

    def sign_up() -> tuple[TestClient, uuid.UUID]:
        owner = make_client()
        body = {"business_name": "Test Shop", "email": f"{uuid.uuid4().hex}@example.com", "password": GOOD_PASSWORD}
        response = owner.post("/api/v1/signup", json=body)
        assert response.status_code == 201, response.text
        return owner, uuid.UUID(response.json()["business_id"])

    return sign_up


@dataclass
class Shop:
    """A Business ready to chat: it has a Service, Working Hours, and a chat slug."""

    slug: str
    business_id: uuid.UUID


@pytest.fixture
def shop(sign_up_owner) -> Shop:
    # Imported here, not at the top: that test module imports this file (no import loop).
    from tests.integration.test_tenant_isolation import _setup

    owner, business_id = sign_up_owner()
    return Shop(slug=_setup(owner)["chat_slug"], business_id=business_id)


def assert_not_found(response) -> None:
    """Our own 404 (FR-11). A plain "no such address" 404 from the router does not count."""
    assert response.status_code == 404, response.text
    assert response.json() == {"error": {"code": "not_found", "message": "We could not find that."}}


def _owner_membership(business_id: uuid.UUID) -> Membership:
    # A direct database read, outside the app's tenant rules, so the test sees the truth.
    with Session(get_engine()) as session:
        return session.scalars(select(Membership).where(Membership.business_id == business_id)).one()


def membership_of(business_id: uuid.UUID) -> uuid.UUID:
    """The id of the Owner's membership row in this Business."""
    return _owner_membership(business_id).id


def membership_is_active(business_id: uuid.UUID) -> bool:
    """Is the Owner's membership in this Business still active?"""
    return _owner_membership(business_id).is_active


def set_owner_roles(business_id: uuid.UUID, roles: list[str]) -> None:
    """Give the one membership in this Business new Roles (a direct database write).

    The session cookie stays valid: the next request reads the new Roles.
    """
    with Session(get_engine()) as session, session.begin():
        session.execute(update(Membership).where(Membership.business_id == business_id).values(roles=roles))


@dataclass
class Member:
    """A team member who joined through an invite (story 2.5)."""

    client: TestClient  # logged in as this member
    email: str
    membership_id: uuid.UUID


def membership_id_for_email(email: str) -> uuid.UUID:
    """A direct database read: the membership of the User with this email."""
    with Session(get_engine()) as session:
        query = select(Membership.id).join(User, User.id == Membership.user_id).where(User.email == email)
        return session.scalars(query).one()


@pytest.fixture
def invite_member(make_client):
    """Invite a new person into the Owner's Business, and accept as them. Returns a Member.

    After this, the Business has 2+ memberships: do NOT use membership_of,
    membership_is_active or set_owner_roles on it (they assume one membership).
    """

    def invite(owner: TestClient, roles: list[str]) -> Member:
        email = f"{uuid.uuid4().hex}@example.com"
        created = owner.post("/api/v1/team/invites", json={"email": email, "roles": roles})
        assert created.status_code == 201, created.text
        member = make_client()
        accepted = member.post(
            "/api/v1/invites/accept", json={"token": created.json()["token"], "password": GOOD_PASSWORD}
        )
        assert accepted.status_code == 200, accepted.text
        return Member(client=member, email=email, membership_id=membership_id_for_email(email))

    return invite

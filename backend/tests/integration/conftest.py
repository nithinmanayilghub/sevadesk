# Integration test fixtures: a real Postgres in Docker, migrated, plus an API client.
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.valkey import ValkeyContainer

from app.core.db import get_engine
from app.core.redis_client import get_redis
from app.core.settings import get_settings
from app.core.telemetry import add_span_exporter, flush_telemetry
from app.main import app

# alembic.ini lives in backend/, two folders above this file's folder.
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


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
    yield
    # Close pooled connections so nothing is left open after the test.
    get_engine().dispose()


@pytest.fixture
def client(migrated_db):
    return TestClient(app)

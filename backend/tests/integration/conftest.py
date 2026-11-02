# Integration test fixtures: a real Postgres in Docker, migrated, plus an API client.
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.valkey import ValkeyContainer

from app.core.db import get_engine
from app.core.redis_client import get_redis
from app.core.settings import get_settings
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


@pytest.fixture
def client(pg, redis_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg.get_connection_url())
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("APP_VERSION", "test-1")
    # Settings and engine are cached, so clear them to pick up the env vars above.
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_redis.cache_clear()
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    yield TestClient(app)
    # Close pooled connections so nothing is left open after the test.
    get_engine().dispose()

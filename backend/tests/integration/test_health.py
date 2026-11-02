# Tests for GET /api/health: both dependencies up, each one down, and recovery.
from app.core.db import get_engine
from app.core.redis_client import get_redis
from app.core.settings import get_settings

BAD_DB = "postgresql+psycopg://x:x@127.0.0.1:1/x"  # port 1 refuses at once
BAD_REDIS = "redis://127.0.0.1:1/0"


def clear_caches():
    # Settings, engine and Redis client are cached; clear so new env vars are used.
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_redis.cache_clear()


def error_body(message):
    return {"error": {"code": "dependency_unavailable", "message": message}}


def test_health_ok(client):
    # Behaviour: both reachable -> 200 and each dependency says ok.
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "redis": "ok"}


def test_health_database_down(client, monkeypatch):
    # Behaviour: Postgres unreachable -> 503 envelope naming database.
    monkeypatch.setenv("DATABASE_URL", BAD_DB)
    clear_caches()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == error_body("Not reachable: database")


def test_health_redis_down(client, monkeypatch):
    # Behaviour: Valkey unreachable -> 503 envelope naming redis.
    monkeypatch.setenv("REDIS_URL", BAD_REDIS)
    clear_caches()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == error_body("Not reachable: redis")


def test_health_both_down(client, monkeypatch):
    # Behaviour: both unreachable -> 503 envelope naming both, database first.
    monkeypatch.setenv("DATABASE_URL", BAD_DB)
    monkeypatch.setenv("REDIS_URL", BAD_REDIS)
    clear_caches()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == error_body("Not reachable: database, redis")


def test_health_recovers_after_database_returns(client, monkeypatch):
    # Behaviour: once Postgres is reachable again, health goes back to 200.
    good_db = get_settings().database_url
    monkeypatch.setenv("DATABASE_URL", BAD_DB)
    clear_caches()
    assert client.get("/api/health").status_code == 503
    monkeypatch.setenv("DATABASE_URL", good_db)
    clear_caches()
    assert client.get("/api/health").status_code == 200


def test_openapi_lists_health(client):
    schema = client.get("/api/openapi.json").json()
    assert "/api/health" in schema["paths"]

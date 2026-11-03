# Tests for the worker heartbeat and GET /api/health/worker.
# NOTE: app.worker is imported inside tests (not at the top) because importing it
# builds a queue from REDIS_URL; the `client` fixture must set that env var first.
import asyncio

import redis.asyncio

from app.core.db import get_engine
from app.core.health import HEARTBEAT_KEY
from app.core.redis_client import get_redis
from app.core.settings import get_settings

BAD_REDIS = "redis://127.0.0.1:1/0"  # port 1 refuses at once


def clear_caches():
    # Settings, engine and Redis client are cached; clear so new env vars are used.
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_redis.cache_clear()


def beat(redis_url):
    # Run the worker's heartbeat job once, the way the worker would.
    from app.worker import write_heartbeat

    async def run():
        conn = redis.asyncio.Redis.from_url(redis_url)
        try:
            await write_heartbeat({"redis": conn})
        finally:
            await conn.aclose()

    asyncio.run(run())


def test_worker_health_ok_after_heartbeat(client, redis_url):
    # Behaviour: a heartbeat written by the worker makes the endpoint 200.
    beat(redis_url)
    try:
        response = client.get("/api/health/worker")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        get_redis().delete(HEARTBEAT_KEY)


def test_worker_health_503_without_heartbeat(client):
    # Behaviour: no heartbeat key -> 503 worker_unavailable.
    get_redis().delete(HEARTBEAT_KEY)
    response = client.get("/api/health/worker")
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "worker_unavailable",
            "message": "No worker heartbeat in the last 30 seconds",
        }
    }


def test_heartbeat_has_ttl(client, redis_url):
    # Behaviour: the heartbeat expires, so a dead worker is noticed.
    beat(redis_url)
    try:
        assert 0 < get_redis().ttl(HEARTBEAT_KEY) <= 30
    finally:
        get_redis().delete(HEARTBEAT_KEY)


def test_worker_health_503_when_redis_down(client, monkeypatch):
    # Behaviour: Valkey unreachable -> 503 dependency_unavailable.
    monkeypatch.setenv("REDIS_URL", BAD_REDIS)
    clear_caches()
    response = client.get("/api/health/worker")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "dependency_unavailable", "message": "Not reachable: redis"}}


def test_worker_settings_schedule_heartbeat(client):
    # Behaviour: the worker runs write_heartbeat every 10 seconds.
    from app import worker

    job = worker.settings["cron_jobs"][0]
    assert job.function is worker.write_heartbeat
    assert job.cron == "* * * * * */10"

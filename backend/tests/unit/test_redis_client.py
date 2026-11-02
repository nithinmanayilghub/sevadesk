# The Redis client must give up quickly, so a dead Valkey cannot hang a request.
from app.core.redis_client import get_redis
from app.core.settings import get_settings


def test_redis_client_has_timeouts(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()
    get_redis.cache_clear()
    kwargs = get_redis().connection_pool.connection_kwargs
    assert kwargs["socket_connect_timeout"] == 2
    assert kwargs["socket_timeout"] == 2
    get_settings.cache_clear()
    get_redis.cache_clear()

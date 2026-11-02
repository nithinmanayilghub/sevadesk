# The Redis/Valkey client: one shared client, with short timeouts so a dead server cannot hang us.
from functools import lru_cache

import redis

from app.core.settings import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    # Cached: one client (one connection pool) for the whole app.
    # Tests call get_redis.cache_clear() after changing REDIS_URL.
    return redis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=2,  # give up connecting after 2 seconds
        socket_timeout=2,  # give up waiting for a reply after 2 seconds
    )

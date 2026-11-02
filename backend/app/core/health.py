# Health checks: can we reach Postgres and Valkey? Each returns True or False, never raises.
import redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_engine
from app.core.redis_client import get_redis


def check_database() -> bool:
    try:
        with get_engine().begin() as connection:
            # SET LOCAL limits only this transaction (this health query),
            # not other app queries. A stuck Postgres is cut off after 2 s.
            connection.execute(text("SET LOCAL statement_timeout = '2s'"))
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def check_redis() -> bool:
    try:
        return bool(get_redis().ping())
    except redis.RedisError:
        return False


# The worker writes this key every 10 s; it expires after 30 s.
# So "key exists" means "a worker was alive in the last 30 s".
HEARTBEAT_KEY = "health:worker:heartbeat"
HEARTBEAT_TTL_SECONDS = 30


def check_worker_heartbeat() -> bool:
    # A redis.RedisError is NOT caught here: the route turns it into a 503.
    return get_redis().exists(HEARTBEAT_KEY) == 1

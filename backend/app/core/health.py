# Health checks: can we reach Postgres and Valkey? Each returns True or False, never raises.
import redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_engine
from app.core.redis_client import get_redis


def check_database() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def check_redis() -> bool:
    try:
        return bool(get_redis().ping())
    except redis.RedisError:
        return False

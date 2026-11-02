# Database plumbing: the engine, the model base class, and the per-request session.
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.settings import get_settings


class Base(DeclarativeBase):
    # Every table model inherits from this, so Alembic can see all tables.
    pass


@lru_cache
def get_engine() -> Engine:
    # One engine (one connection pool) for the whole app.
    return create_engine(get_settings().database_url)


def get_session() -> Iterator[Session]:
    # AD-15: the entry point (this request) owns the transaction.
    # session.begin() commits when the request succeeds and rolls back on error.
    # Services only use the session; they never call commit themselves.
    with Session(get_engine()) as session, session.begin():
        yield session

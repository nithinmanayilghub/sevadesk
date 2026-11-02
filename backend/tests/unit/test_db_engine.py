# The engine must test pooled connections before use and give up connecting after 2 s.
import sqlalchemy

from app.core import db
from app.core.settings import get_settings


def test_engine_has_pre_ping_and_connect_timeout(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/d")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()
    db.get_engine.cache_clear()

    # connect_args are not stored on the engine in a readable way, so we wrap
    # create_engine to record what get_engine passes to it.
    seen = {}

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return sqlalchemy.create_engine(*args, **kwargs)

    monkeypatch.setattr(db, "create_engine", spy)
    engine = db.get_engine()

    assert seen["connect_args"]["connect_timeout"] == 2
    assert seen["pool_pre_ping"] is True
    assert engine.pool._pre_ping is True

    engine.dispose()
    get_settings.cache_clear()
    db.get_engine.cache_clear()

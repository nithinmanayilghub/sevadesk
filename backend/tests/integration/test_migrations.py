# Integration tests: the migration history is linear and every migration can be undone.
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from tests.integration.conftest import ALEMBIC_INI

from app.core.db import get_engine


def test_alembic_has_one_head():
    # Behaviour: the migration history never splits into two branches.
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1


def test_migrations_downgrade_to_base_and_back(client):
    # Behaviour: every migration can be undone, and redoing them restores the app.
    config = Config(str(ALEMBIC_INI))

    command.downgrade(config, "base")
    tables = set(inspect(get_engine()).get_table_names())
    assert tables <= {"alembic_version"}

    command.upgrade(config, "head")
    tables = set(inspect(get_engine()).get_table_names())
    assert tables == {"alembic_version", "app_meta", "businesses", "users", "sessions", "memberships"}

    response = client.get("/api/v1/hello")
    assert response.status_code == 200
    assert response.json()["message"] == "Namaste from SevaDesk"

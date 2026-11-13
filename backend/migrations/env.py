# Alembic environment: tells Alembic which database and which models to use.
from alembic import context
from sqlalchemy import create_engine

import app.core.app_meta  # noqa: F401  (importing registers the AppMeta model)
import app.modules.accounts.models  # noqa: F401  (users, sessions, memberships)
import app.modules.business.models  # noqa: F401  (businesses)
from app.core.db import Base
from app.core.settings import get_settings

target_metadata = Base.metadata


def run_migrations_online() -> None:
    # The URL comes from our Settings (env var), never from alembic.ini.
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()

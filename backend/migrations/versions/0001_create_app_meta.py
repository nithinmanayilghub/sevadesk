# Migration 0001: create the app_meta table and insert the one "hello" row.
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    app_meta = op.create_table(
        "app_meta",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.UniqueConstraint("key", name="uq_app_meta_key"),
    )
    op.bulk_insert(
        app_meta,
        [{"id": uuid.uuid7(), "key": "hello", "value": "Hello from SevaDesk"}],
    )


def downgrade() -> None:
    op.drop_table("app_meta")

# Migration 0002: update the hello message.

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE app_meta SET value = 'Namaste from SevaDesk' WHERE key='hello'")


def downgrade() -> None:
    op.execute("UPDATE app_meta SET value = 'Hello from SevaDesk' WHERE key='hello'")

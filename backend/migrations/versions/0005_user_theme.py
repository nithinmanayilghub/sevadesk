# Migration 0005: users.theme (Story 2.6). Every User, old and new, starts on "system".
# The constraint name is written out by hand, as in 0004.
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default fills the column for existing Users, so nullable=False is safe.
    op.add_column("users", sa.Column("theme", sa.Text(), server_default="system", nullable=False))
    op.create_check_constraint("ck_users_theme_valid", "users", "theme IN ('system','light','dark')")


def downgrade() -> None:
    op.drop_constraint("ck_users_theme_valid", "users", type_="check")
    op.drop_column("users", "theme")

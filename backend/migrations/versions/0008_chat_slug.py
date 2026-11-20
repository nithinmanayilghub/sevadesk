# Migration 0008: the chat slug (Story 3.3, FR-14), the last part of the Chat Page link /c/{slug}.
# Three steps, because a NOT NULL column cannot be added to a table that already has rows:
# 1. add it as nullable, 2. fill the old rows, 3. make it NOT NULL and UNIQUE.
# The old rows get "chat-" + 6 hex chars, made in SQL: a migration must not import app code
# (make_chat_slug), because app code can change later and old migrations must not.
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("businesses", sa.Column("chat_slug", sa.Text(), nullable=True))
    op.execute("UPDATE businesses SET chat_slug = 'chat-' || substr(md5(id::text), 1, 6)")
    op.alter_column("businesses", "chat_slug", nullable=False)
    op.create_unique_constraint("uq_businesses_chat_slug", "businesses", ["chat_slug"])


def downgrade() -> None:
    op.drop_constraint("uq_businesses_chat_slug", "businesses", type_="unique")
    op.drop_column("businesses", "chat_slug")

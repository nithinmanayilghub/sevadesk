# Migration 0010: conversations.last_message_at and the Inbox order index (Story 4.3, FR-23).
# Old Conversations get the time of their newest Message; one with no Message (none exist in
# practice, but the database allows it) gets its own created_at.
# The index texts are copied here, not imported from app code: old migrations must not change
# when app code changes later. They match the model's Index in inbox/models.py.
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add it empty, 2. fill it, 3. then make it required (a NOT NULL column cannot start empty).
    op.add_column("conversations", sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE conversations c SET last_message_at = COALESCE("
        "(SELECT max(m.created_at) FROM messages m"
        " WHERE m.business_id = c.business_id AND m.conversation_id = c.id),"
        " c.created_at)"
    )
    op.alter_column("conversations", "last_message_at", nullable=False, server_default=sa.func.now())
    op.create_index(
        "ix_conversations_inbox_order",
        "conversations",
        ["business_id", sa.text("(state = 'handoff') DESC"), sa.text("last_message_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_inbox_order", table_name="conversations")
    op.drop_column("conversations", "last_message_at")

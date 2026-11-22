# Migration 0009: the inbox tables (Story 4.1, FR-15): customers, visitor_tokens,
# conversations, messages. All tenant tables owned by inbox.
# Constraint names are written out by hand, as in 0006/0007 (op.create_table skips the convention).
# The CHECK texts are copied here, not imported from app code: old migrations must not change
# when app code changes later.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _id_and_tenant(table: str) -> list:
    """The columns and rules every tenant table starts with."""
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name=f"fk_{table}_business_id_businesses"),
        sa.UniqueConstraint("business_id", "id", name=f"uq_{table}_business_id_id"),
    ]


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table("customers", *_id_and_tenant("customers"), _created_at())
    op.create_table(
        "visitor_tokens",
        *_id_and_tenant("visitor_tokens"),
        sa.Column("token_hash", sa.Text(), nullable=False),
        _created_at(),
        sa.UniqueConstraint("business_id", "token_hash", name="uq_visitor_tokens_business_id_token_hash"),
    )
    op.create_table(
        "conversations",
        *_id_and_tenant("conversations"),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("visitor_token_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Text(), server_default="agent", nullable=False),
        sa.Column("last_seq", sa.Integer(), server_default="0", nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["business_id", "customer_id"],
            ["customers.business_id", "customers.id"],
            name="fk_conversations_business_id_customers",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "visitor_token_id"],
            ["visitor_tokens.business_id", "visitor_tokens.id"],
            name="fk_conversations_business_id_visitor_tokens",
        ),
        sa.CheckConstraint("state IN ('agent', 'handoff', 'closed')", name="ck_conversations_state_valid"),
        sa.CheckConstraint("last_seq >= 0", name="ck_conversations_last_seq_valid"),
    )
    # "This browser's newest chat" is looked up on every Chat Page load.
    op.create_index("ix_conversations_visitor_token_id", "conversations", ["business_id", "visitor_token_id"])
    op.create_table(
        "messages",
        *_id_and_tenant("messages"),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("author_type", sa.Text(), nullable=False),
        sa.Column("author_membership_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("lang", sa.Text(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=True),
        sa.Column("actions", JSONB(), server_default="[]", nullable=False),
        _created_at(),
        sa.UniqueConstraint(
            "business_id", "conversation_id", "seq", name="uq_messages_business_id_conversation_id_seq"
        ),
        sa.UniqueConstraint(
            "business_id",
            "conversation_id",
            "client_message_id",
            name="uq_messages_business_id_conversation_id_client_message_id",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "conversation_id"],
            ["conversations.business_id", "conversations.id"],
            name="fk_messages_business_id_conversations",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "author_membership_id"],
            ["memberships.business_id", "memberships.id"],
            name="fk_messages_business_id_memberships",
        ),
        sa.CheckConstraint(
            "author_type IN ('customer', 'agent', 'user', 'system')", name="ck_messages_author_type_valid"
        ),
        sa.CheckConstraint(
            "(author_type = 'user') = (author_membership_id IS NOT NULL)", name="ck_messages_member_only_for_user"
        ),
        sa.CheckConstraint("lang IN ('en', 'hi')", name="ck_messages_lang_valid"),
        sa.CheckConstraint("char_length(body) > 0", name="ck_messages_body_not_empty"),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_index("ix_conversations_visitor_token_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("visitor_tokens")
    op.drop_table("customers")

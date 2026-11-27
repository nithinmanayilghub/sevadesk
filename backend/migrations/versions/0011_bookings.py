# Migration 0011: the bookings table (Story 5.1, AR-1, AD-9). A tenant table owned by bookings.
# Constraint names are written out by hand, as in 0009 (op.create_table skips the convention).
# The CHECK texts are copied here, not imported from app code: old migrations must not change
# when app code changes later. They match bookings/models.py.
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("technician_membership_id", sa.Uuid(), nullable=True),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_bookings"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_bookings_business_id_businesses"),
        sa.UniqueConstraint("business_id", "id", name="uq_bookings_business_id_id"),
        sa.ForeignKeyConstraint(
            ["business_id", "customer_id"],
            ["customers.business_id", "customers.id"],
            name="fk_bookings_business_id_customers",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "conversation_id"],
            ["conversations.business_id", "conversations.id"],
            name="fk_bookings_business_id_conversations",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "technician_membership_id"],
            ["memberships.business_id", "memberships.id"],
            name="fk_bookings_business_id_memberships",
        ),
        sa.CheckConstraint(
            "state IN ('requested', 'confirmed', 'declined', 'expired', 'completed', 'cancelled')",
            name="ck_bookings_state_valid",
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_bookings_ends_after_starts"),
        sa.CheckConstraint("price_paise > 0", name="ck_bookings_price_valid"),
        sa.CheckConstraint("state <> 'requested' OR expires_at IS NOT NULL", name="ck_bookings_request_has_expiry"),
        sa.CheckConstraint(
            "state NOT IN ('confirmed', 'completed', 'cancelled') OR technician_membership_id IS NOT NULL",
            name="ck_bookings_technician_when_confirmed",
        ),
    )
    op.create_index("ix_bookings_business_id_starts_at", "bookings", ["business_id", "starts_at"])


def downgrade() -> None:
    op.drop_index("ix_bookings_business_id_starts_at", table_name="bookings")
    op.drop_table("bookings")

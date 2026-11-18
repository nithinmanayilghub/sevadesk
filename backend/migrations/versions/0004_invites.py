# Migration 0004: the invites table (Story 2.5, FR-9). A tenant table owned by accounts.
# Constraint names are written out by hand, as in 0003 (op.create_table skips the convention).
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("roles", ARRAY(sa.Text()), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_invites"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_invites_business_id_businesses"),
        sa.UniqueConstraint("token_hash", name="uq_invites_token_hash"),
        sa.UniqueConstraint("business_id", "id", name="uq_invites_business_id_id"),
        sa.CheckConstraint(
            "cardinality(roles) > 0 AND roles <@ ARRAY['staff','technician']::text[]",
            name="ck_invites_roles_valid",
        ),
    )


def downgrade() -> None:
    op.drop_table("invites")

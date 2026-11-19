# Migration 0006: the services table (Story 3.1, FR-12). A tenant table owned by business.
# Constraint names are written out by hand, as in 0004 (op.create_table skips the convention).
# The numbers (30, 480, 100000000) are written out too, on purpose: a migration is a frozen
# snapshot, so it must not change when the constants in models.py change later.
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_services"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_services_business_id_businesses"),
        sa.UniqueConstraint("business_id", "id", name="uq_services_business_id_id"),
        sa.CheckConstraint("duration_minutes BETWEEN 30 AND 480", name="ck_services_duration_valid"),
        sa.CheckConstraint("price_paise > 0 AND price_paise <= 100000000", name="ck_services_price_valid"),
    )


def downgrade() -> None:
    op.drop_table("services")

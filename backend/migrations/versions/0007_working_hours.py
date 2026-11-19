# Migration 0007: Working Hours and closed days (Story 3.2, FR-13), plus the Business timezone.
# - businesses.timezone: how to read the Business's clock times (AR-5). Default Asia/Kolkata.
# - working_hours, closed_days: tenant tables owned by business.
# Constraint names are written out by hand, as in 0006 (op.create_table skips the convention).
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default also fills the column for Businesses that already exist.
    op.add_column("businesses", sa.Column("timezone", sa.Text(), server_default="Asia/Kolkata", nullable=False))
    op.create_table(
        "working_hours",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_working_hours"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_working_hours_business_id_businesses"),
        sa.UniqueConstraint("business_id", "id", name="uq_working_hours_business_id_id"),
        sa.UniqueConstraint("business_id", "weekday", name="uq_working_hours_business_id_weekday"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_working_hours_weekday_valid"),
        sa.CheckConstraint("end_time > start_time", name="ck_working_hours_end_after_start"),
    )
    op.create_table(
        "closed_days",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_closed_days"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_closed_days_business_id_businesses"),
        sa.UniqueConstraint("business_id", "id", name="uq_closed_days_business_id_id"),
        sa.UniqueConstraint("business_id", "day", name="uq_closed_days_business_id_day"),
    )


def downgrade() -> None:
    op.drop_table("closed_days")
    op.drop_table("working_hours")
    op.drop_column("businesses", "timezone")

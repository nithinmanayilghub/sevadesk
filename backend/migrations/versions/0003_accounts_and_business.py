# Migration 0003: businesses, users, sessions, memberships (Story 2.1).
# Constraint names are written out by hand: op.create_table does not apply the naming
# convention. The sign-up code relies on the name uq_users_email.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_businesses"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        _created_at(),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id_users"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("roles", ARRAY(sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], name="fk_memberships_business_id_businesses"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_memberships_user_id_users"),
        sa.UniqueConstraint("user_id", name="uq_memberships_user_id"),
        sa.UniqueConstraint("business_id", "id", name="uq_memberships_business_id_id"),
        sa.CheckConstraint(
            "cardinality(roles) > 0 AND roles <@ ARRAY['owner','staff','technician']::text[]",
            name="ck_memberships_roles_valid",
        ),
    )


def downgrade() -> None:
    # Reverse order, because of the foreign keys.
    op.drop_table("memberships")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("businesses")

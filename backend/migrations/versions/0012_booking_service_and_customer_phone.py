# Migration 0012 (Story 5.2): the first Booking write needs two more facts.
# - bookings.service_id: which Service the job is for. NOT NULL is safe: no code wrote Bookings
#   before this story, so the table is empty everywhere.
# - customers.name and customers.phone: a phone-in Customer is found again by phone, inside one
#   Business. Both stay NULL for chat Customers.
# Constraint names are written out by hand, as in 0009 and 0011.
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("service_id", sa.Uuid(), nullable=False))
    op.create_foreign_key(
        "fk_bookings_business_id_services",
        "bookings",
        "services",
        ["business_id", "service_id"],
        ["business_id", "id"],
    )
    op.add_column("customers", sa.Column("name", sa.Text(), nullable=True))
    op.add_column("customers", sa.Column("phone", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_customers_business_id_phone", "customers", ["business_id", "phone"])


def downgrade() -> None:
    op.drop_constraint("uq_customers_business_id_phone", "customers", type_="unique")
    op.drop_column("customers", "phone")
    op.drop_column("customers", "name")
    op.drop_constraint("fk_bookings_business_id_services", "bookings", type_="foreignkey")
    op.drop_column("bookings", "service_id")

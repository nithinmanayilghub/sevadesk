# Tables owned by the bookings module (story 5.1, AR-1).
# - bookings: one job at one time for one Customer. A tenant table (AD-3).
#
# bookings never imports inbox (no import cycle). It keeps customer_id and conversation_id as
# plain ids. The DATABASE still checks them: every link is a composite foreign key
# (business_id, x_id), so a Booking in Business A can never point at a row of Business B.
#
# Booking states (AD-10): requested -> confirmed | declined | expired,
#                         confirmed -> completed | cancelled.
# Only bookings functions change the state (AD-9). This story only READS Bookings.
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.repository import TenantModel

BOOKING_STATES = ("requested", "confirmed", "declined", "expired", "completed", "cancelled")
# These states always have a Technician. A request (Epic 6) gets one only when Staff confirm it.
STATES_WITH_TECHNICIAN = ("confirmed", "completed", "cancelled")


def _in(values: tuple[str, ...]) -> str:
    """SQL text for a list: ('a', 'b')."""
    return f"({', '.join(repr(value) for value in values)})"


class Booking(TenantModel):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),  # the tenant-table rule (core/repository.py)
        ForeignKeyConstraint(["business_id", "customer_id"], ["customers.business_id", "customers.id"]),
        # A phone-in Booking has no Conversation. A NULL conversation_id skips this check.
        ForeignKeyConstraint(["business_id", "conversation_id"], ["conversations.business_id", "conversations.id"]),
        ForeignKeyConstraint(
            ["business_id", "technician_membership_id"], ["memberships.business_id", "memberships.id"]
        ),
        CheckConstraint(f"state IN {_in(BOOKING_STATES)}", name="state_valid"),
        CheckConstraint("ends_at > starts_at", name="ends_after_starts"),
        CheckConstraint("price_paise > 0", name="price_valid"),
        # "Live" is worked out from expires_at (AD-9): requested AND expires_at > now. With NULL,
        # "NULL > now" is never true, so the request would never hold its Slot (a double booking).
        CheckConstraint("state <> 'requested' OR expires_at IS NOT NULL", name="request_has_expiry"),
        CheckConstraint(
            f"state NOT IN {_in(STATES_WITH_TECHNICIAN)} OR technician_membership_id IS NOT NULL",
            name="technician_when_confirmed",
        ),
        # Slot math reads "this Business's Bookings in this time range".
        Index("ix_bookings_business_id_starts_at", "business_id", "starts_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    state: Mapped[str] = mapped_column(Text)
    # Moments in UTC (timestamptz, AR-5). Slot math turns them into Business-local times.
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    customer_id: Mapped[uuid.UUID]
    conversation_id: Mapped[uuid.UUID | None]
    technician_membership_id: Mapped[uuid.UUID | None]
    # The Price agreed for this job, in whole paise (AR-5). Kept here, so a later Price change
    # of the Service does not change old Bookings.
    price_paise: Mapped[int]
    # Only for requests: after this moment the request no longer holds its Slot (AD-9).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

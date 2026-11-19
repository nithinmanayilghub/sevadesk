# Tables owned by the business module (AR-1).
# - businesses: global (it is the tenant itself).
# - services: a tenant table; each row belongs to one Business (story 3.1, FR-12).
# - working_hours, closed_days: tenant tables for the weekly hours and holidays (story 3.2, FR-13).
import uuid
from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.repository import TenantModel

# FR-12 limits. schemas.py imports these, so the API and the database use the same numbers.
MIN_DURATION = 30  # minutes
MAX_DURATION = 480  # minutes (8 hours)
# ₹10,00,000 in paise. Well inside Postgres "integer" (max 2,147,483,647), so no overflow.
MAX_PRICE_PAISE = 100_000_000


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    name: Mapped[str]
    # How to read this Business's clock times, e.g. "10:00" in Working Hours (AR-5).
    # server_default here too, not only in the migration: without it SQLAlchemy would send
    # an explicit NULL on sign-up, and the NOT NULL rule would refuse the new Business.
    timezone: Mapped[str] = mapped_column(Text, server_default="Asia/Kolkata")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Service(TenantModel):
    """A job type the Business sells, with a duration and a Price (FR-12).

    Never deleted: deactivate it instead (is_active = false), so later Bookings
    that point at it stay valid.
    """

    __tablename__ = "services"
    __table_args__ = (
        # Lets other tenant tables (bookings, later) point here with a (business_id, id) key (AD-3).
        UniqueConstraint("business_id", "id"),
        # The second guard: even a bug in the API cannot save a bad duration or Price.
        CheckConstraint(f"duration_minutes BETWEEN {MIN_DURATION} AND {MAX_DURATION}", name="duration_valid"),
        CheckConstraint(f"price_paise > 0 AND price_paise <= {MAX_PRICE_PAISE}", name="price_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    name: Mapped[str] = mapped_column(Text)
    duration_minutes: Mapped[int]
    # Money is a whole number of paise (₹1 = 100 paise), never a float (AR-5).
    price_paise: Mapped[int]
    is_active: Mapped[bool] = mapped_column(server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkingHours(TenantModel):
    """The open hours of one weekday (FR-13). A closed weekday has NO row.

    Times are clock times in the Business timezone ("10:00 every Monday"), not moments,
    so they are `time`, not `timestamptz` (AR-5). Slot math (Epic 4) turns them into moments.
    """

    __tablename__ = "working_hours"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),  # the tenant-table rule (core/repository.py)
        UniqueConstraint("business_id", "weekday"),  # one range per day: no split shifts
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_valid"),
        # No overnight hours: the day must end after it starts (latest end 23:59).
        CheckConstraint("end_time > start_time", name="end_after_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday … 6 = Sunday (date.weekday())
    start_time: Mapped[time]
    end_time: Mapped[time]


class ClosedDay(TenantModel):
    """One date the Business is closed (a holiday), whatever the weekly hours say (FR-13)."""

    __tablename__ = "closed_days"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),
        UniqueConstraint("business_id", "day"),  # a date is closed once, not twice
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    day: Mapped[date]

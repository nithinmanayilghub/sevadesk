# Database access for the bookings table (story 5.1). A tenant repository: the base adds
# "WHERE business_id = <current Business>" to every query (AD-3).
import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, and_, func, or_, select

from app.core.repository import TenantRepository
from app.core.tenancy import current_business_id
from app.modules.bookings.models import Booking


def is_live(now: datetime) -> ColumnElement[bool]:
    """THE rule for "this Booking holds its Slot" (AD-9, AR-14). Every count must use it.

    Live = confirmed, or a request that has not expired yet. "Expired" is worked out here, on
    read, from expires_at: a request past its expires_at stops counting at once, even before
    the hourly sweep (a later story) writes state = 'expired'. Declined, expired, completed and
    cancelled Bookings never count.
    """
    return or_(
        Booking.state == "confirmed",
        and_(Booking.state == "requested", Booking.expires_at > now),
    )


# The first number of the capacity lock's two-number key. Any fixed number works: it keeps our
# lock apart from any other advisory lock the app may take later (story 5.2, AD-9).
BOOKINGS_LOCK_NAMESPACE = 1001


class BookingRepository(TenantRepository[Booking]):
    model = Booking

    def take_capacity_lock(self) -> None:
        """Wait for, then hold, THIS Business's capacity lock until the transaction ends (AD-9).

        pg_advisory_xact_lock(namespace, key) is a lock on a pair of numbers, not on a row. A
        second transaction that asks for the same pair waits until the first commits or rolls
        back. Then its recount sees the first one's Booking.
        - The key is a hash of business_id: Businesses never wait for each other.
        - "xact" = transaction-level: Postgres releases it at commit or rollback by itself, so
          it can never leak (a session-level lock would stay held on a pooled connection).
        - Taking it twice in one transaction is fine: Postgres just counts it twice.
        """
        key = func.hashtext(str(current_business_id()))
        self.session.execute(select(func.pg_advisory_xact_lock(BOOKINGS_LOCK_NAMESPACE, key)))

    def technician_busy(self, technician_id: uuid.UUID, start: datetime, end: datetime) -> bool:
        """True when this Technician already has a CONFIRMED job that overlaps [start, end) (AD-9).

        Half-open ranges, like the Slot math: a job ending at 11:00 does not clash with 11:00.
        """
        query = self._select().where(
            Booking.technician_membership_id == technician_id,
            Booking.state == "confirmed",
            Booking.starts_at < end,
            Booking.ends_at > start,
        )
        return self.session.scalars(query.limit(1)).first() is not None

    def live_between(self, start: datetime, end: datetime, now: datetime) -> list[tuple[datetime, datetime]]:
        """(starts_at, ends_at) of every live Booking that overlaps [start, end)."""
        query = self._select().where(is_live(now), Booking.starts_at < end, Booking.ends_at > start)
        return [(row.starts_at, row.ends_at) for row in self.session.scalars(query)]

# Database access for the bookings table (story 5.1). A tenant repository: the base adds
# "WHERE business_id = <current Business>" to every query (AD-3).
from datetime import datetime

from sqlalchemy import ColumnElement, and_, or_

from app.core.repository import TenantRepository
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


class BookingRepository(TenantRepository[Booking]):
    model = Booking

    def live_between(self, start: datetime, end: datetime, now: datetime) -> list[tuple[datetime, datetime]]:
        """(starts_at, ends_at) of every live Booking that overlaps [start, end)."""
        query = self._select().where(is_live(now), Booking.starts_at < end, Booking.ends_at > start)
        return [(row.starts_at, row.ends_at) for row in self.session.scalars(query)]

# Database access for the business module. Only business's own files use it (AD-2).
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.repository import TenantRepository
from app.core.tenancy import current_business_id
from app.modules.business.chat_slug import make_chat_slug
from app.modules.business.models import Business, ClosedDay, Service, WorkingHours


class BusinessRepository:
    # businesses is a global table (it is the tenant itself), so no tenant filter here.
    def __init__(self, session: Session):
        self.session = session

    def add(self, name: str) -> Business:
        # Every new Business gets its chat slug here, so no caller can forget it.
        business = Business(name=name, chat_slug=make_chat_slug(name))
        self.session.add(business)
        self.session.flush()  # fills business.id now
        return business

    def find_by_chat_slug(self, chat_slug: str) -> Business | None:
        # The public Chat Page starts here: the slug, not a session, names the Business (AD-3 b).
        return self.session.scalars(select(Business).where(Business.chat_slug == chat_slug)).one_or_none()

    def get_current(self, for_update: bool = False) -> Business:
        """The Business of the current tenant scope.

        for_update=True locks its row until the transaction ends (SELECT ... FOR UPDATE).
        Two saves at the same moment then run one after the other, not on top of each other.
        """
        query = select(Business).where(Business.id == current_business_id())
        if for_update:
            query = query.with_for_update()
        return self.session.scalars(query).one()


class ServiceRepository(TenantRepository[Service]):
    # A tenant table: the base adds "WHERE business_id = <current Business>" to every query.
    model = Service

    def list_all(self) -> list[Service]:
        # Oldest first. id breaks ties: two rows saved in the same instant keep one fixed order.
        query = self._select().order_by(Service.created_at, Service.id)
        return list(self.session.scalars(query))

    def list_active(self) -> list[Service]:
        # Only what the Business really sells now: deactivated Services are not offered (FR-12).
        query = self._select().where(Service.is_active).order_by(Service.created_at, Service.id)
        return list(self.session.scalars(query))


class WorkingHoursRepository(TenantRepository[WorkingHours]):
    # One row per OPEN weekday. A closed weekday has no row.
    model = WorkingHours

    def list_week(self) -> list[WorkingHours]:
        return list(self.session.scalars(self._select().order_by(WorkingHours.weekday)))

    def has_any(self) -> bool:
        # At least one open weekday (a closed weekday has no row).
        return self.session.scalars(self._select().limit(1)).first() is not None

    def for_weekday(self, weekday: int) -> WorkingHours | None:
        return self.session.scalars(self._select().where(WorkingHours.weekday == weekday)).one_or_none()

    def replace_week(self, rows: list[WorkingHours]) -> None:
        """Delete this Business's week, then insert the new open days.

        ONE direct DELETE statement first, not session.delete() per row: in one flush
        SQLAlchemy sends INSERTs before DELETEs, and the new Monday would clash with the old
        one (UNIQUE business_id, weekday). The tenant filter is written by hand here, because
        _select() only builds SELECTs; check_replace_working_hours (isolation suite) guards it.
        """
        business_id = current_business_id()
        self.session.execute(delete(WorkingHours).where(WorkingHours.business_id == business_id))
        for row in rows:
            row.business_id = business_id
        self.session.add_all(rows)
        self.session.flush()  # send the INSERTs now, so a database error shows inside the request


class ClosedDayRepository(TenantRepository[ClosedDay]):
    # One row per closed date (holiday).
    model = ClosedDay

    def list_from(self, day: date) -> list[ClosedDay]:
        # From this date on, soonest first: past holidays do not pile up on the page.
        query = self._select().where(ClosedDay.day >= day).order_by(ClosedDay.day)
        return list(self.session.scalars(query))

    def exists(self, day: date) -> bool:
        return self.session.scalars(self._select().where(ClosedDay.day == day)).first() is not None

    def remove(self, row: ClosedDay) -> None:
        self.session.delete(row)
        self.session.flush()  # send the DELETE now, inside the request

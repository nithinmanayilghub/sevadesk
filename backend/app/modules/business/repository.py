# Database access for the business module. Only business's own files use it (AD-2).
from sqlalchemy.orm import Session

from app.core.repository import TenantRepository
from app.modules.business.models import Business, Service


class BusinessRepository:
    # businesses is a global table (it is the tenant itself), so no tenant filter here.
    def __init__(self, session: Session):
        self.session = session

    def add(self, name: str) -> Business:
        business = Business(name=name)
        self.session.add(business)
        self.session.flush()  # fills business.id now
        return business


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

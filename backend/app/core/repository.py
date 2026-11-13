# The tenant-scoped base repository (AD-3).
# Every tenant table inherits TenantModel; every tenant repository extends TenantRepository.
# The base adds "WHERE business_id = <current Business>" to every query and sets
# business_id on every insert. Repository methods never take business_id from callers.
import uuid

from sqlalchemy import ForeignKey, Select, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base
from app.core.tenancy import current_business_id


class TenantModel(Base):
    """Base for tables that belong to one Business."""

    __abstract__ = True

    # A string FK ("businesses.id"), so core does not import the business module.
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"))


class TenantRepository[ModelT: TenantModel]:
    model: type[ModelT]  # each subclass sets its model, e.g. model = Membership

    def __init__(self, session: Session):
        self.session = session

    def _select(self) -> Select[tuple[ModelT]]:
        # The one place the tenant filter is added. Subclass queries start here.
        return select(self.model).where(self.model.business_id == current_business_id())

    def get(self, id: uuid.UUID) -> ModelT | None:
        return self.session.scalars(self._select().where(self.model.id == id)).one_or_none()

    def add(self, row: ModelT) -> ModelT:
        # Always the current Business: a caller cannot choose another one.
        row.business_id = current_business_id()
        self.session.add(row)
        # flush sends the INSERT now, so row.id is filled and constraint errors show here.
        self.session.flush()
        return row

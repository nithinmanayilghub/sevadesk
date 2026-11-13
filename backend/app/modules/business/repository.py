# Database access for businesses. A global table, so no tenant filter.
from sqlalchemy.orm import Session

from app.modules.business.models import Business


class BusinessRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, name: str) -> Business:
        business = Business(name=name)
        self.session.add(business)
        self.session.flush()  # fills business.id now
        return business

# Database guards for the services table (story 3.1, FR-12, AR-5).
# These tests write rows directly, past the API, to prove the database ITSELF refuses bad data.
# The API checks the same rules first (test_services.py); this is the second guard.
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.modules.business.models import Service


def insert(business_id: uuid.UUID, **fields) -> Service:
    """Save one Service row in its OWN session: a failed INSERT spoils a session until rollback."""
    values = {"name": "Fan repair", "duration_minutes": 60, "price_paise": 49900, **fields}
    with Session(get_engine(), expire_on_commit=False) as session, session.begin():
        row = Service(business_id=business_id, **values)
        session.add(row)
    return row


def test_service_is_saved_active_with_integer_paise(sign_up_owner):
    _, business_id = sign_up_owner()
    row = insert(business_id)
    with Session(get_engine()) as session:
        saved = session.get(Service, row.id)
        assert saved.is_active is True  # the database default: a new Service is active
        assert saved.price_paise == 49900
        assert type(saved.price_paise) is int  # money is a whole number of paise, never a float


@pytest.mark.parametrize("minutes", [29, 481])
def test_database_refuses_bad_duration(sign_up_owner, minutes):
    _, business_id = sign_up_owner()
    with pytest.raises(IntegrityError, match="ck_services_duration_valid"):
        insert(business_id, duration_minutes=minutes)


@pytest.mark.parametrize("paise", [0, 100_000_001])
def test_database_refuses_bad_price(sign_up_owner, paise):
    _, business_id = sign_up_owner()
    with pytest.raises(IntegrityError, match="ck_services_price_valid"):
        insert(business_id, price_paise=paise)


def test_database_refuses_missing_price(sign_up_owner):
    _, business_id = sign_up_owner()
    with pytest.raises(IntegrityError, match="price_paise"):
        insert(business_id, price_paise=None)

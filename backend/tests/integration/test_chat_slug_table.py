# Database guards for businesses.chat_slug (story 3.3, FR-14). These tests write rows directly,
# past the API, to prove the database ITSELF keeps every slug unique.
import re

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.modules.business.models import Business


def test_new_business_gets_a_slug(sign_up_owner):
    _, business_id = sign_up_owner()  # "Test Shop"
    with Session(get_engine()) as session:
        slug = session.get(Business, business_id).chat_slug
    assert re.fullmatch(r"test-shop-[a-hj-km-np-z2-9]{6}", slug)


def test_database_refuses_a_duplicate_slug(migrated_db):
    with Session(get_engine()) as session, session.begin():
        session.add(Business(name="First", chat_slug="same-abcdef"))
    # Its OWN session: a failed INSERT spoils a session until rollback.
    with pytest.raises(IntegrityError, match="uq_businesses_chat_slug"):
        with Session(get_engine()) as session, session.begin():
            session.add(Business(name="Second", chat_slug="same-abcdef"))

# Database rules for the users.theme column (story 2.6). Every User starts on "system",
# and the database itself refuses any value that is not system, light or dark.
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.db import get_engine

pytestmark = pytest.mark.isolation


def owner_user_id(business_id):
    """Find the Owner's user id through their membership in this Business."""
    with get_engine().begin() as conn:
        sql = text("SELECT user_id FROM memberships WHERE business_id = :id")
        return conn.execute(sql, {"id": business_id}).scalar_one()


def test_new_user_theme_is_system(sign_up_owner):
    # Behaviour: a brand new User starts on the "system" theme.
    _client, business_id = sign_up_owner()
    user_id = owner_user_id(business_id)
    with get_engine().begin() as conn:
        theme = conn.execute(text("SELECT theme FROM users WHERE id = :id"), {"id": user_id}).scalar_one()
    assert theme == "system"


def test_database_refuses_unknown_theme(sign_up_owner):
    # Behaviour: the database itself refuses a theme that is not system, light or dark.
    _client, business_id = sign_up_owner()
    user_id = owner_user_id(business_id)
    with pytest.raises(IntegrityError), get_engine().begin() as conn:
        conn.execute(text("UPDATE users SET theme = 'blue' WHERE id = :id"), {"id": user_id})

# Database rules for the invites table (story 2.5, FR-9). The database itself refuses bad
# rows, so even a bug in the app cannot store an invite that makes a second Owner.
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.core.tenancy import tenant_scope
from app.modules.accounts.models import Invite
from app.modules.accounts.repository import InviteRepository

pytestmark = pytest.mark.isolation


def add_invite(business_id: uuid.UUID, roles: list[str]) -> Invite:
    """Insert one invite row for this Business, straight through the repository."""
    with Session(get_engine()) as session, session.begin(), tenant_scope(business_id):
        invite = InviteRepository(session).add(
            Invite(
                email=f"{uuid.uuid4().hex}@example.com",
                roles=roles,
                token_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
        session.expunge(invite)  # keep the loaded values after the session closes
        return invite


def test_invite_with_owner_role_is_refused(sign_up_owner):
    # Behaviour: the database itself refuses an invite that would make a second Owner.
    _, business_id = sign_up_owner()
    with pytest.raises(IntegrityError):
        add_invite(business_id, ["owner"])


def test_invite_with_no_roles_is_refused(sign_up_owner):
    # Behaviour: an invite must give at least one Role.
    _, business_id = sign_up_owner()
    with pytest.raises(IntegrityError):
        add_invite(business_id, [])


def test_staff_and_technician_invite_is_stored(sign_up_owner):
    # Behaviour: a normal invite saves, and starts unused.
    _, business_id = sign_up_owner()
    invite = add_invite(business_id, ["staff", "technician"])
    assert invite.business_id == business_id
    assert invite.used_at is None

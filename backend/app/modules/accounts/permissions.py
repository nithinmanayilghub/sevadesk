# Role-based access (story 2.4, FR-10, AD-4). The FR-10 table lives here, once.
# Services call require_roles(actor, permission) first, before they read or change anything.
# Other modules reach these functions through accounts/service.py (the front door, AD-2).
import uuid

from app.core.errors import Forbidden
from app.modules.accounts.schemas import Actor, Permission, Role

# The FR-10 table: which Roles may do each action. A User may do an action if ANY one of
# their Roles is listed (a User with Staff + Technician gets the rights of both).
ALLOWED_ROLES: dict[Permission, frozenset[Role]] = {
    # Manage Services, Working Hours, and team: Owner only.
    Permission.MANAGE_SETUP: frozenset({Role.OWNER}),
    # Use the Inbox and approve Bookings: Owner and Staff.
    Permission.USE_INBOX_AND_BOOKINGS: frozenset({Role.OWNER, Role.STAFF}),
    # See own assigned Bookings: everyone.
    Permission.SEE_OWN_BOOKINGS: frozenset({Role.OWNER, Role.STAFF, Role.TECHNICIAN}),
    # See the Dashboard: Owner and Staff (Staff without team settings: that is MANAGE_SETUP).
    Permission.SEE_DASHBOARD: frozenset({Role.OWNER, Role.STAFF}),
    # See and delete a Customer's data (NFR-8, not an FR-10 row): Owner only. A delete cannot
    # be undone, so only the person responsible for the Business's data may do it.
    Permission.MANAGE_CUSTOMER_DATA: frozenset({Role.OWNER}),
}


def _allows(roles: set[Role], permission: Permission) -> bool:
    # True when the two sets share at least one Role.
    return not roles.isdisjoint(ALLOWED_ROLES[permission])


def permissions_for(roles: set[Role]) -> list[Permission]:
    """Everything these Roles may do, in the table's order. The app uses it to hide things."""
    return [permission for permission in Permission if _allows(roles, permission)]


def require_roles(actor: Actor, permission: Permission) -> None:
    """The one Role check (AR-7). Raises Forbidden (403) if no Role of the Actor may do this."""
    if not _allows(actor.roles, permission):
        raise Forbidden()


def assigned_bookings_filter(actor: Actor) -> uuid.UUID | None:
    """Which Bookings this Actor may see (AD-4: a Technician-only Actor sees only their own).

    Returns the Actor's membership id when they may NOT approve Bookings (Technician-only):
    the bookings module then keeps only rows with technician_membership_id == that id.
    Returns None for Owner and Staff: they approve Bookings, so they see them all.
    """
    if _allows(actor.roles, Permission.USE_INBOX_AND_BOOKINGS):
        return None
    return actor.membership_id

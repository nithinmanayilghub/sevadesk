# The business front door (AD-2). Other modules call only these functions.
# - sign_up: the whole sign-up flow (FR-7).
# - Services (story 3.1, FR-12): the Owner's list / add / replace, and list_active_services
#   for the Chat Page and the Agent (later stories).
# - Working Hours (story 3.2, FR-13): the Owner's weekly hours and closed dates, and
#   hours_on for slot math (Epic 5) and the Agent.
# - Chat Page (story 3.3, FR-14): the Owner's setup status, and the public Chat Page.
#   find_chat_business turns a slug into a Business for every public chat route (story 4.1).
import re
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, FieldError, NotFound
from app.core.tenancy import tenant_scope

# Import the module, not the function, so every call goes through accounts_service.<name>.
from app.modules.accounts import service as accounts_service
from app.modules.accounts.schemas import Actor, Permission
from app.modules.business.models import Business, ClosedDay, Service, WorkingHours
from app.modules.business.repository import (
    BusinessRepository,
    ClosedDayRepository,
    ServiceRepository,
    WorkingHoursRepository,
)
from app.modules.business.schemas import (
    WEEKDAYS,
    ChatBusiness,
    ChatPageOut,
    ChatServiceOut,
    ClosedDayIn,
    ClosedDayList,
    ClosedDayOut,
    InboxFacts,
    OpenHours,
    ServiceIn,
    ServiceList,
    ServiceOut,
    SetupOut,
    SignupRequest,
    SignupResponse,
    WeekIn,
    WorkingHoursOut,
)


def sign_up(session: Session, request: SignupRequest) -> tuple[SignupResponse, str]:
    """Create the Business and its Owner, and log the Owner in. Returns (response, session token)."""
    # One transaction (owned by the request, AD-15): if any step fails, nothing is saved.
    business = BusinessRepository(session).add(request.business_name)
    # The tenant is server-derived: this transaction just created it.
    with tenant_scope(business.id):
        owner = accounts_service.create_owner(session, request.email, request.password)
    # A new Owner is logged in at once (story 2.2).
    token = accounts_service.start_session(session, owner.user_id)
    return SignupResponse(business_id=business.id, business_name=business.name), token


def _out(row: Service) -> ServiceOut:
    return ServiceOut(
        service_id=row.id,
        name=row.name,
        duration_minutes=row.duration_minutes,
        price_paise=row.price_paise,
        is_active=row.is_active,
    )


def list_services(session: Session, actor: Actor) -> ServiceList:
    """Every Service of the Owner's Business, active or not, oldest first."""
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    return ServiceList(services=[_out(row) for row in ServiceRepository(session).list_all()])


def create_service(session: Session, actor: Actor, data: ServiceIn) -> ServiceOut:
    """Add a Service. No commit here: the request owns the transaction (AD-15)."""
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    row = ServiceRepository(session).add(
        Service(
            name=data.name,
            duration_minutes=data.duration_minutes,
            price_paise=data.price_paise,
            is_active=data.is_active,
        )
    )
    return _out(row)


def replace_service(session: Session, actor: Actor, service_id: uuid.UUID, data: ServiceIn) -> ServiceOut:
    """Replace every field of one Service. Deactivate = is_active False. Never deletes (FR-12)."""
    # Role check FIRST: a 403 then says nothing about whether this id exists (story 2.4).
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    # The tenant filter hides other Businesses' Services: their ids answer 404 (FR-11).
    row = ServiceRepository(session).get_or_raise(service_id)
    row.name = data.name
    row.duration_minutes = data.duration_minutes
    row.price_paise = data.price_paise
    row.is_active = data.is_active
    session.flush()  # send the UPDATE now, so a database error shows here, inside the request
    return _out(row)


def list_active_services(session: Session) -> list[ServiceOut]:
    """What the Business really offers now (FR-12). For the Chat Page and the Agent.

    No Role check: Customers see these too. The caller must already be in a tenant scope.
    """
    return [_out(row) for row in ServiceRepository(session).list_active()]


# ---------------------------------------------------------------- working hours (story 3.2, FR-13)


def _week_out(session: Session) -> WorkingHoursOut:
    business = BusinessRepository(session).get_current()
    days: dict[str, OpenHours | None] = dict.fromkeys(WEEKDAYS)  # every day closed ...
    for row in WorkingHoursRepository(session).list_week():  # ... until a row says it is open
        days[WEEKDAYS[row.weekday]] = OpenHours(start_time=row.start_time, end_time=row.end_time)
    return WorkingHoursOut(timezone=business.timezone, **days)


def get_working_hours(session: Session, actor: Actor) -> WorkingHoursOut:
    """The Owner's week: each day's hours, or None when closed, plus the Business timezone."""
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    return _week_out(session)


def replace_working_hours(session: Session, actor: Actor, week: WeekIn) -> WorkingHoursOut:
    """Replace the whole week. No commit here: the request owns the transaction (AD-15)."""
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    # Lock the Business row: a second save at the same moment waits for this one to finish.
    BusinessRepository(session).get_current(for_update=True)
    rows = [
        WorkingHours(weekday=weekday, start_time=day.start_time, end_time=day.end_time)
        for weekday, name in enumerate(WEEKDAYS)
        if (day := getattr(week, name)) is not None  # a closed day (None) gets no row
    ]
    WorkingHoursRepository(session).replace_week(rows)
    return _week_out(session)


# ---------------------------------------------------------------- closed days (story 3.2, FR-13)

DAY_TAKEN = "This date is already closed."


def _today(business: Business) -> date:
    """Today's date on the Business's own clock (AR-5), not the server's (UTC).

    At 1:00 am in India it is still "yesterday" in UTC. The one place "today" is worked out,
    so tests can replace it with a fixed date.
    """
    return datetime.now(ZoneInfo(business.timezone)).date()


def _day_error(message: str) -> AppError:
    return AppError(
        code="validation_error",
        message="Some fields need fixing.",
        status_code=422,
        fields=[FieldError(field="day", message=message)],
    )


def _closed_out(row: ClosedDay) -> ClosedDayOut:
    return ClosedDayOut(closed_day_id=row.id, day=row.day)


def list_closed_days(session: Session, actor: Actor) -> ClosedDayList:
    """Closed dates from today on (Business timezone), soonest first."""
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    today = _today(BusinessRepository(session).get_current())
    return ClosedDayList(closed_days=[_closed_out(row) for row in ClosedDayRepository(session).list_from(today)])


def add_closed_day(session: Session, actor: Actor, data: ClosedDayIn) -> ClosedDayOut:
    """Close one date, whatever the weekly hours say. Refuses past and already-closed dates."""
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    # Lock the Business row: two adds of the same date at once run one after the other.
    business = BusinessRepository(session).get_current(for_update=True)
    if data.day < _today(business):
        raise _day_error("Pick today or a later date.")
    repository = ClosedDayRepository(session)
    if repository.exists(data.day):
        raise _day_error(DAY_TAKEN)
    try:
        row = repository.add(ClosedDay(day=data.day))
    except IntegrityError as exc:
        # The second guard: the UNIQUE rule. Same answer as the check above, never a 500.
        if "uq_closed_days_business_id_day" in str(exc.orig):
            raise _day_error(DAY_TAKEN) from exc
        raise
    return _closed_out(row)


def remove_closed_day(session: Session, actor: Actor, closed_day_id: uuid.UUID) -> None:
    """Open a closed date again. The weekly hours then apply to it."""
    # Role check FIRST: a 403 then says nothing about whether this id exists (story 2.4).
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    repository = ClosedDayRepository(session)
    repository.remove(repository.get_or_raise(closed_day_id))  # another Business's id -> 404


def hours_on(session: Session, day: date) -> OpenHours | None:
    """The open hours on one date, or None when closed. For slot math (Epic 4) and the Agent.

    A closed date wins over the weekly hours, so it is checked first. No Role check:
    Customers' bookings depend on it too. The caller must already be in a tenant scope.
    """
    if ClosedDayRepository(session).exists(day):
        return None
    row = WorkingHoursRepository(session).for_weekday(day.weekday())
    return None if row is None else OpenHours(start_time=row.start_time, end_time=row.end_time)


# ---------------------------------------------------------------- chat page (story 3.3, FR-14)

# The only shape a slug can have. Checked BEFORE any database query, so odd input
# (a NUL character, 500 letters) is a plain 404, never a database error (500).
_SLUG_SHAPE = re.compile(r"[a-z0-9-]{1,40}")


def _is_set_up(session: Session) -> tuple[bool, bool]:
    """(has an active Service, has Working Hours). The caller must be in a tenant scope."""
    return bool(ServiceRepository(session).list_active()), WorkingHoursRepository(session).has_any()


def get_setup(session: Session, actor: Actor) -> SetupOut:
    """The Owner's chat slug, and which setup steps are done (the Dashboard checklist)."""
    accounts_service.require_roles(actor, Permission.MANAGE_SETUP)
    has_services, has_working_hours = _is_set_up(session)
    return SetupOut(
        chat_slug=BusinessRepository(session).get_current().chat_slug,
        has_services=has_services,
        has_working_hours=has_working_hours,
    )


def find_chat_business(session: Session, chat_slug: str) -> ChatBusiness:
    """The Business a public chat link names, or NotFound. Every public chat route starts here.

    The tenant comes from the slug ONLY (AD-3 b): even a logged-in Owner of another
    Business gets the Business this slug names. business/dependencies.py calls this.
    """
    chat_slug = chat_slug.lower()  # a link typed in upper case still works
    if not _SLUG_SHAPE.fullmatch(chat_slug):
        raise NotFound()
    business = BusinessRepository(session).find_by_chat_slug(chat_slug)
    if business is None:
        raise NotFound()  # same answer as a bad shape: says nothing about which slugs exist
    return ChatBusiness(business_id=business.id, name=business.name)


def get_chat_page(session: Session, business: ChatBusiness) -> ChatPageOut:
    """The public Chat Page: the Business name and its active Services. No login.

    The caller (ChatBusinessDep) already entered this Business's tenant scope.
    """
    services = [
        ChatServiceOut(name=row.name, duration_minutes=row.duration_minutes, price_paise=row.price_paise)
        for row in ServiceRepository(session).list_active()
    ]
    has_services, has_working_hours = _is_set_up(session)
    return ChatPageOut(
        business_name=business.name,
        taking_requests=has_services and has_working_hours,
        services=services,
    )


def inbox_facts(session: Session) -> InboxFacts:
    """The current Business's chat slug and timezone, for the Inbox (story 4.3).

    No Role check here: inbox calls it only after its own check (USE_INBOX_AND_BOOKINGS).
    """
    business = BusinessRepository(session).get_current()
    return InboxFacts(chat_slug=business.chat_slug, timezone=business.timezone)

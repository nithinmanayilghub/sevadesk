# The inbox front door (AD-2). Other modules call only these functions.
# - poll_conversation: a Conversation's new Messages + snapshot + cursor (story 4.2, AD-7).
#   The Chat Page poll (chat_poll.py) calls it on its slow path.
# - receive_message: save one Customer Message, once, with the next seq (AR-12, AR-13).
# - start_handoff / end_handoff: the ONLY code that changes a Conversation's state (AD-10,
#   AR-15; a unit test guards this). reply / take_over / give_back call them (story 4.4).
# - customer_details / delete_customer: the Customer detail sheet and the DPDP delete (story 4.5).
#
# This file is channel-neutral (NFR-9): it gets a Channel (channel.py) and never sees a
# cookie or a phone number. No commit here: the request owns the transaction (AD-15).
#
# Lock order: the Channel takes its own locks first (webchat: the visitor-token row), then
# returns the Conversation row locked. Any new flow takes them in the same order.
import uuid

import redis
from opentelemetry import trace
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.core.rate_limit import AttemptLimiter
from app.core.redis_client import get_redis
from app.core.tenancy import current_business_id
from app.core.versions import mark_conversation_changed, read_or_seed_version, read_version
from app.modules.accounts import service as accounts_service
from app.modules.accounts.schemas import Actor, Permission
from app.modules.business import service as business_service
from app.modules.inbox.channel import Channel
from app.modules.inbox.models import Conversation, Customer, Message, VisitorToken
from app.modules.inbox.repository import (
    ConversationRepository,
    CustomerRepository,
    MessageRepository,
    VisitorTokenRepository,
)
from app.modules.inbox.schemas import (
    ChatCursor,
    ChatPollOut,
    ChatSnapshot,
    ConversationStateOut,
    CustomerOut,
    InboxCursor,
    InboxPage,
    InboxRow,
    MessageOut,
    NeedsHumanCount,
    SendMessageIn,
    detect_lang,
    preview,
)

# Send limits (NFR-5), counted in Redis. Per IP is high on purpose: Indian mobile carriers put
# many phones behind one IP address (CGNAT). Both count per Business (AD-3 key rule).
CHAT_SEND_IP_LIMIT = 120
CHAT_SEND_CONVERSATION_LIMIT = 30
CHAT_SEND_WINDOW_SECONDS = 600  # 10 minutes; also how long the lock lasts
CHAT_UNAVAILABLE = "Chat is not available right now. Please try again."


class TooManyMessages(AppError):
    def __init__(self, retry_after: int):
        super().__init__(
            code="too_many_messages",
            message="You are sending messages too fast. Please wait a few minutes.",
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )


def chat_send_ip_limiter() -> AttemptLimiter:
    """Per IP, per Business. The router counts it BEFORE any database work. Key: "<business_id>:<ip>"."""
    return AttemptLimiter(get_redis(), "chat_send:ip", CHAT_SEND_IP_LIMIT, CHAT_SEND_WINDOW_SECONDS, CHAT_UNAVAILABLE)


def chat_send_conversation_limiter() -> AttemptLimiter:
    """Per Conversation. Key: "<business_id>:<conversation_id>"."""
    return AttemptLimiter(
        get_redis(), "chat_send:conv", CHAT_SEND_CONVERSATION_LIMIT, CHAT_SEND_WINDOW_SECONDS, CHAT_UNAVAILABLE
    )


def _out(row: Message) -> MessageOut:
    return MessageOut(
        seq=row.seq,
        author_type=row.author_type,
        body=row.body,
        lang=row.lang,
        client_message_id=row.client_message_id,
        actions=row.actions,
        created_at=row.created_at,
    )


def chat_unavailable() -> AppError:
    """The 503 for a Redis failure on a chat route (fail closed, like the limiters)."""
    return AppError("dependency_unavailable", CHAT_UNAVAILABLE, 503)


def poll_conversation(session: Session, conversation: Conversation | None, after_seq: int) -> ChatPollOut:
    """A Conversation's Messages after after_seq, a snapshot, and a new cursor.

    Channel-neutral: the caller finds the Conversation (Channel.find_conversation), or passes
    None before the first Message. Writes nothing to Postgres (AD-5). Run inside the tenant scope.
    """
    if conversation is None:
        return ChatPollOut(changed=True, messages=[], snapshot=None, cursor=None)
    business_id = current_business_id()
    # The order rule (core/versions.py): the version FIRST, then the Messages. A send that
    # commits in between leaves us with an older version, so the next poll reads again.
    try:
        version = read_or_seed_version(business_id, conversation.id)
    except redis.RedisError as error:
        raise chat_unavailable() from error
    # Read the row AGAIN, after the version (story 4.4). The caller loaded it earlier; a
    # take-over that committed in between would give an OLD state with a NEW version, and
    # every later poll would then say "no change" while the screen shows the wrong state.
    session.refresh(conversation)
    rows = MessageRepository(session).list_after(conversation.id, after_seq)
    # The newest seq we really send. Not conversation.last_seq: that was read by an earlier
    # query and can be older than a row this query saw (each query sees the newest commits).
    # min(): a forged, too-high after_seq comes back down, so new Messages are never hidden.
    next_seq = rows[-1].seq if rows else min(after_seq, conversation.last_seq)
    return ChatPollOut(
        changed=True,
        messages=[_out(row) for row in rows],
        snapshot=ChatSnapshot(conversation_state=conversation.state),
        cursor=ChatCursor(business_id=business_id, after_seq=next_seq, version=version).format(),
    )


def receive_message(session: Session, channel: Channel, data: SendMessageIn) -> MessageOut:
    """Save one Customer Message, or return it if this client_message_id was already saved."""
    # 1. The sender's Conversation, LOCKED: other writers to it wait until we commit.
    conversation = channel.open_conversation(session)
    messages = MessageRepository(session)

    # 2. A retry of a Message we already saved (the answer got lost): hand back the same one.
    #    Checked BEFORE the limit, so a retry is never refused as "too many".
    existing = messages.find_by_client_id(conversation.id, data.client_message_id)
    if existing is not None:
        return _out(existing)

    # 3. Count it (count first, like log-in: many sends at once cannot all slip past 0).
    wait = chat_send_conversation_limiter().hit(f"{current_business_id()}:{conversation.id}")
    if wait is not None:
        raise TooManyMessages(retry_after=wait)  # the rollback undoes anything step 1 made

    # 4. Save it with the next number, and tell open screens.
    return _append(
        session,
        conversation,
        Message(
            author_type="customer",
            body=data.body,
            lang=detect_lang(data.body),
            client_message_id=data.client_message_id,
        ),
    )


def _append(session: Session, conversation: Conversation, message: Message) -> MessageOut:
    """Save one Message at the end of a Conversation. The caller holds the row lock.

    Shared by the Customer send and the team reply, so both number, sort, and announce a
    Message the same way.
    """
    # The next number. Safe because we hold the row lock: nobody else can take it meanwhile.
    conversation.last_seq += 1
    message.conversation_id = conversation.id
    message.seq = conversation.last_seq
    row = MessageRepository(session).add(message)
    # add() flushed the INSERT; refresh reads back created_at and actions the database filled in.
    session.refresh(row)
    # The Inbox order (story 4.3). max(): now() is when the transaction STARTED, so a send that
    # started earlier but waited for the lock can save later with an older time. Never go back.
    conversation.last_message_at = max(conversation.last_message_at, row.created_at)
    # Open Chat Pages and Inbox screens must see it: raise the version, after the commit (AD-7).
    mark_conversation_changed(session, conversation.id)
    return _out(row)


# ---------------------------------------------------------------- Conversation state (AD-10)
# Two rules for both setters:
# - The caller holds the Conversation row lock, so two members clicking at once go in line.
# - No real change -> no version bump: open screens are told "changed" only when it did.


def _state_changed(session: Session, conversation: Conversation, old_state: str) -> None:
    """After a real state change: tell open screens, and note it in this request's trace."""
    mark_conversation_changed(session, conversation.id)
    # A timed note in the trace: only the two states, no person and no text.
    trace.get_current_span().add_event("conversation.state_changed", {"from": old_state, "to": conversation.state})


def start_handoff(session: Session, conversation: Conversation) -> None:
    """A person takes the chat: the Agent stops replying (FR-21). From any state, also closed
    (the Customer wrote again). Already handoff: nothing changes."""
    if conversation.state != "handoff":
        old_state = conversation.state
        conversation.state = "handoff"
        _state_changed(session, conversation, old_state)


def end_handoff(session: Session, conversation: Conversation) -> None:
    """Give the chat back to the Agent (FR-21). Only from handoff: agent or closed stay as they are."""
    if conversation.state == "handoff":
        conversation.state = "agent"
        _state_changed(session, conversation, "handoff")


def _locked_for_member(session: Session, actor: Actor, conversation_id: uuid.UUID) -> Conversation:
    """The Conversation a team member acts on, LOCKED. The Role check comes first, so a
    Technician never learns whether an id exists. Another Business's id is a 404, never a 403."""
    accounts_service.require_roles(actor, Permission.USE_INBOX_AND_BOOKINGS)
    conversation = ConversationRepository(session).lock(conversation_id)
    if conversation is None:
        raise NotFound()
    return conversation


def reply(session: Session, actor: Actor, conversation_id: uuid.UUID, data: SendMessageIn) -> MessageOut:
    """Save a team member's reply (FR-24). Replying starts a Handoff: the Agent pauses."""
    conversation = _locked_for_member(session, actor, conversation_id)
    # A retry of a reply we already saved (the answer got lost): hand back the same one.
    existing = MessageRepository(session).find_by_client_id(conversation.id, data.client_message_id)
    if existing is not None:
        return _out(existing)
    start_handoff(session, conversation)
    return _append(
        session,
        conversation,
        Message(
            author_type="user",
            author_membership_id=actor.membership_id,
            body=data.body,
            lang=detect_lang(data.body),
            client_message_id=data.client_message_id,
        ),
    )


def poll_for_member(session: Session, actor: Actor, conversation_id: uuid.UUID, cursor: str | None) -> ChatPollOut:
    """One open Conversation in the Inbox: what changed since the cursor (AD-7, same shape as
    the Chat Page poll). Writes nothing to Postgres.

    Fast path, Redis only: the cursor's Business must be the actor's (a cursor is only a
    claim), and the version key is built from the ACTOR's Business, never the cursor's. A
    version key exists only for a Conversation that its own Business has polled or changed,
    so another Business's id never matches here and goes on to the slow path's 404.
    """
    accounts_service.require_roles(actor, Permission.USE_INBOX_AND_BOOKINGS)
    parsed = ChatCursor.parse(cursor)
    ours = parsed is not None and parsed.business_id == actor.business_id
    if ours:
        try:
            unchanged = read_version(actor.business_id, conversation_id) == parsed.version
        except redis.RedisError as error:
            raise chat_unavailable() from error
        if unchanged:
            return ChatPollOut(changed=False, messages=[], snapshot=None, cursor=parsed.format())
    # Slow path: Postgres. get_or_raise hides other Businesses' rows: a 404 for them.
    conversation = ConversationRepository(session).get_or_raise(conversation_id)
    return poll_conversation(session, conversation, parsed.after_seq if ours else 0)


def take_over(session: Session, actor: Actor, conversation_id: uuid.UUID) -> ConversationStateOut:
    """The Handoff bar's "Take over" (UX-DR12)."""
    conversation = _locked_for_member(session, actor, conversation_id)
    start_handoff(session, conversation)
    return ConversationStateOut(state=conversation.state)


def give_back(session: Session, actor: Actor, conversation_id: uuid.UUID) -> ConversationStateOut:
    """The Handoff bar's "Give back to Agent" (UX-DR12)."""
    conversation = _locked_for_member(session, actor, conversation_id)
    end_handoff(session, conversation)
    return ConversationStateOut(state=conversation.state)


INBOX_PAGE_SIZE = 20


class InvalidCursor(AppError):
    def __init__(self):
        super().__init__(code="invalid_cursor", message="This list is out of date. Reload the page.", status_code=422)


def _row(conversation: Conversation, newest: Message) -> InboxRow:
    return InboxRow(
        conversation_id=conversation.id,
        state=conversation.state,
        last_message_preview=preview(newest.body),
        last_message_at=conversation.last_message_at,
    )


def list_inbox(session: Session, actor: Actor, cursor: str | None, limit: int) -> InboxPage:
    """One page of the Inbox: Needs Human first, then newest activity first (FR-23).

    cursor=None is the first page. A page's next_cursor names its last row; the next page
    starts right after that row (keyset paging), so a chat never shows twice or goes missing.
    """
    accounts_service.require_roles(actor, Permission.USE_INBOX_AND_BOOKINGS)
    after = None
    if cursor is not None:
        after = InboxCursor.parse(cursor)
        if after is None:
            raise InvalidCursor()
    rows = ConversationRepository(session).inbox_page(after, limit)
    shown = rows[:limit]
    next_cursor = None
    if len(rows) > limit:  # the extra row came back: there is a next page
        last, _ = shown[-1]
        next_cursor = InboxCursor(
            pinned=last.state == "handoff", last_message_at=last.last_message_at, conversation_id=last.id
        ).format()
    facts = business_service.inbox_facts(session)
    return InboxPage(
        conversations=[_row(conversation, newest) for conversation, newest in shown],
        next_cursor=next_cursor,
        chat_slug=facts.chat_slug,
        timezone=facts.timezone,
    )


# The Inbox poll limit (AD-7: poll endpoints are rate-limited). One budget per team member, for
# the 3 Inbox poll routes. An Inbox tab with a chat open polls 3 routes every 5 s = 36 a minute,
# so 120 a minute is room for 3 tabs (a phone and a laptop, say). A 60 s window keeps a lockout short.
INBOX_POLL_LIMIT = 120
INBOX_POLL_WINDOW_SECONDS = 60


class TooManyInboxPolls(AppError):
    def __init__(self, retry_after: int):
        super().__init__(
            code="too_many_requests",
            message="The inbox is busy. Please try again in a minute.",
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )


def inbox_poll_limiter() -> AttemptLimiter:
    """Per member, per Business. Key: "<business_id>:<membership_id>". Redis down = 503."""
    return AttemptLimiter(
        get_redis(), "inbox_poll", INBOX_POLL_LIMIT, INBOX_POLL_WINDOW_SECONDS, "The inbox is not available right now."
    )


def count_inbox_poll(actor: Actor) -> None:
    """Count one Inbox request. Raises TooManyInboxPolls (429), or 503 if Redis is down."""
    wait = inbox_poll_limiter().hit(f"{actor.business_id}:{actor.membership_id}")
    if wait is not None:
        raise TooManyInboxPolls(retry_after=wait)


def count_needs_human(session: Session, actor: Actor) -> NeedsHumanCount:
    """How many Conversations are in Handoff (Needs Human), for the Inbox tab's red number."""
    accounts_service.require_roles(actor, Permission.USE_INBOX_AND_BOOKINGS)
    return NeedsHumanCount(count=ConversationRepository(session).count_needs_human())


# ---------------------------------------------------------------- Delete a Customer (NFR-8, AD-13)


def customer_details(session: Session, actor: Actor, conversation_id: uuid.UUID) -> CustomerOut:
    """The Customer of this Conversation, for the Customer detail sheet. Owner only.

    The Role check comes first, so Staff and Technicians never learn whether an id exists.
    """
    accounts_service.require_roles(actor, Permission.MANAGE_CUSTOMER_DATA)
    conversation = ConversationRepository(session).get_or_raise(conversation_id)  # 404 if not ours
    customer = CustomerRepository(session).get_or_raise(conversation.customer_id)
    conversations, messages = ConversationRepository(session).count_for_customer(customer.id)
    return CustomerOut(
        customer_id=customer.id,
        created_at=customer.created_at,
        conversation_count=conversations,
        message_count=messages,
    )


def delete_customer(session: Session, actor: Actor, customer_id: uuid.UUID) -> None:
    """Delete a Customer and ALL their data, in this request's one transaction (AD-13, AD-15).

    Either every row goes, or (on any error, the rollback) none does: never a half delete.

    Lock order, the same as a Customer send (webchat.open_conversation): visitor token rows
    first, then Conversation rows. A send that is saving right now holds those locks; we wait
    for it, and then delete its new Message too. Two flows that take locks in the same order
    can only queue, never wait on each other in a circle (a deadlock).
    """
    accounts_service.require_roles(actor, Permission.MANAGE_CUSTOMER_DATA)
    customers, tokens = CustomerRepository(session), VisitorTokenRepository(session)
    conversations, messages = ConversationRepository(session), MessageRepository(session)

    # The Customer row first: a second delete of the same Customer waits here, then gets a 404.
    if customers.lock(customer_id) is None:
        raise NotFound()  # missing, already deleted, or another Business's (the filter hides it)

    # Which visitor tokens are theirs: the ones their Conversations point at. A token's
    # Conversations always belong to ONE Customer (open_conversation makes the Customer and the
    # Conversation together), so deleting these tokens takes nobody else's chat.
    token_ids = conversations.visitor_token_ids_of(customer_id)
    tokens.lock_ids(token_ids)  # lock 1, like a send
    conversation_ids = conversations.lock_for_customer(customer_id)  # lock 2, like a send

    # Epic 5: call bookings.delete_for_customer(customer_id) HERE, before our own rows (AD-13).

    # Children first, parent last: each foreign key still points at a row that exists.
    deleted_messages = messages.delete_where(Message.conversation_id.in_(conversation_ids))
    conversations.delete_where(Conversation.id.in_(conversation_ids))
    tokens.delete_where(VisitorToken.id.in_(token_ids))
    customers.delete_where(Customer.id == customer_id)

    # Open Chat Pages and Inbox screens: their next poll must not say "no change" (AD-7).
    for conversation_id in conversation_ids:
        mark_conversation_changed(session, conversation_id)
    # A timed note in this request's trace: counts only, no ids and no text (NFR-8).
    trace.get_current_span().add_event(
        "customer.deleted", {"conversations": len(conversation_ids), "messages": deleted_messages}
    )

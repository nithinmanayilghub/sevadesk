# The inbox front door (AD-2). Other modules call only these functions.
# - list_messages: a Customer's own Conversation (story 4.1, FR-15).
# - receive_message: save one Customer Message, once, with the next seq (AR-12, AR-13).
#
# This file is channel-neutral (NFR-9): it gets a Channel (channel.py) and never sees a
# cookie or a phone number. No commit here: the request owns the transaction (AD-15).
#
# Lock order: the Channel takes its own locks first (webchat: the visitor-token row), then
# returns the Conversation row locked. Any new flow takes them in the same order.
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.rate_limit import AttemptLimiter
from app.core.redis_client import get_redis
from app.core.tenancy import current_business_id
from app.core.versions import mark_conversation_changed
from app.modules.inbox.channel import Channel
from app.modules.inbox.models import Message
from app.modules.inbox.repository import MessageRepository
from app.modules.inbox.schemas import ChatMessagesOut, MessageOut, SendMessageIn, detect_lang

# Send limits (NFR-5), counted in Redis. Per IP is high on purpose: Indian mobile carriers put
# many phones behind one IP address (CGNAT). Both count per Business (AD-3 key rule).
CHAT_SEND_IP_LIMIT = 120
CHAT_SEND_CONVERSATION_LIMIT = 30
CHAT_SEND_WINDOW_SECONDS = 600  # 10 minutes; also how long the lock lasts
_CHAT_UNAVAILABLE = "Chat is not available right now. Please try again."


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
    return AttemptLimiter(get_redis(), "chat_send:ip", CHAT_SEND_IP_LIMIT, CHAT_SEND_WINDOW_SECONDS, _CHAT_UNAVAILABLE)


def chat_send_conversation_limiter() -> AttemptLimiter:
    """Per Conversation. Key: "<business_id>:<conversation_id>"."""
    return AttemptLimiter(
        get_redis(), "chat_send:conv", CHAT_SEND_CONVERSATION_LIMIT, CHAT_SEND_WINDOW_SECONDS, _CHAT_UNAVAILABLE
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


def list_messages(session: Session, channel: Channel) -> ChatMessagesOut:
    """The sender's own Conversation, oldest first. Empty before the first send. Writes nothing."""
    conversation = channel.find_conversation(session)
    if conversation is None:
        return ChatMessagesOut(messages=[])
    return ChatMessagesOut(messages=[_out(row) for row in MessageRepository(session).list_for(conversation.id)])


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

    # 4. The next number. Safe because we hold the row lock: nobody else can take it meanwhile.
    conversation.last_seq += 1
    row = messages.add(
        Message(
            conversation_id=conversation.id,
            seq=conversation.last_seq,
            author_type="customer",
            body=data.body,
            lang=detect_lang(data.body),
            client_message_id=data.client_message_id,
        )
    )
    # add() flushed the INSERT; refresh reads back created_at and actions the database filled in.
    session.refresh(row)
    # 5. Open Chat Pages must see it: raise the version, but only after the commit (AD-7).
    mark_conversation_changed(session, conversation.id)
    return _out(row)

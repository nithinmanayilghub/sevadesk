# The Chat Page poll (story 4.2, AD-7). One function, poll_chat, answers
# GET /api/v1/chat/{chat_slug}/messages?cursor=… . The router only hands it the HTTP facts.
#
# Two paths:
# - Fast: cursor + known cookie -> Redis map -> Redis version. Same version = "no change".
#   No Postgres at all.
# - Slow: everything else. Postgres finds the Business (404 for an unknown slug) and the
#   Messages, then writes the map so the next poll can be fast.
#
# AD-3 note: on the fast path the cursor's Business id is only a claim. A map entry proves it,
# and only the slug's own slow path writes one. So the poll is counted only after that proof
# (a forged Business id never gets a counter in Redis).
# Redis down at any step -> 503 (fail closed, like the limiters).
import uuid

import redis
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.rate_limit import AttemptLimiter
from app.core.redis_client import get_redis
from app.core.tenancy import tenant_scope
from app.core.versions import read_version
from app.modules.business.dependencies import chat_business_scope
from app.modules.inbox import service
from app.modules.inbox.schemas import ChatCursor, ChatPollOut
from app.modules.inbox.webchat import WebchatChannel

# Poll limit (AR-12): an open Chat Page polls 12 times a minute, so 600 is many tabs behind
# one carrier IP. Per IP only, no per-Conversation poll limit: a poll writes nothing, and
# NFR-5's per-Conversation limit is on sends (story 4.1).
CHAT_POLL_IP_LIMIT = 600
CHAT_POLL_WINDOW_SECONDS = 60


class TooManyPolls(AppError):
    def __init__(self, retry_after: int):
        super().__init__(
            code="too_many_polls",
            message="Too many requests. Please wait a minute.",
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )


def poll_chat(session: Session, chat_slug: str, token: str | None, cursor: str | None, ip: str) -> ChatPollOut:
    """This browser's chat on this Chat Page: what changed since the cursor.

    token: the visitor cookie's token, or None for a browser we do not know yet (it has no chat).
    cursor: the last answer's cursor, or None. A cursor we did not make counts as None.
    Raises NotFound (404) for an unknown slug, TooManyPolls (429), or 503 if Redis is down.
    """
    try:
        return _poll(session, chat_slug, token, ChatCursor.parse(cursor), ip)
    except redis.RedisError as error:
        raise service.chat_unavailable() from error


def _poll(session: Session, chat_slug: str, token: str | None, parsed: ChatCursor | None, ip: str) -> ChatPollOut:
    slug = chat_slug.lower()  # slugs are lower case; the map stores this form
    channel = WebchatChannel(token) if token is not None else None
    counted = False

    # The fast path: Redis only.
    if parsed is not None and channel is not None:
        conversation_id = channel.cached_conversation(parsed.business_id, slug)
        if conversation_id is not None:
            # Proven now: this browser chats in parsed.business_id via this slug.
            with tenant_scope(parsed.business_id):
                _count(parsed.business_id, ip)
                counted = True
                # A missing version (Redis lost it) is never "unchanged": the slow path seeds one.
                if read_version(parsed.business_id, conversation_id) == parsed.version:
                    return ChatPollOut(changed=False, messages=[], snapshot=None, cursor=parsed.format())

    # The slow path: Postgres. A bad or unknown slug is a 404 here.
    with chat_business_scope(session, chat_slug) as business:
        if not counted:  # a counted fast path proved this same Business: count once only
            _count(business.business_id, ip)
        # A cursor from another Business (the cookie is shared by every slug) starts at 0.
        after_seq = parsed.after_seq if parsed is not None and parsed.business_id == business.business_id else 0
        conversation = channel.find_conversation(session) if channel is not None else None
        answer = service.poll_conversation(session, conversation, after_seq)
        if channel is not None and conversation is not None:
            channel.remember_conversation(slug, conversation.id)  # the next poll can be fast
        return answer


def _count(business_id: uuid.UUID, ip: str) -> None:
    """One poll against the per-IP limit, per Business (count first, like the send limit)."""
    limiter = AttemptLimiter(
        get_redis(), "chat_poll:ip", CHAT_POLL_IP_LIMIT, CHAT_POLL_WINDOW_SECONDS, service.CHAT_UNAVAILABLE
    )
    wait = limiter.hit(f"{business_id}:{ip}")
    if wait is not None:
        raise TooManyPolls(retry_after=wait)

# The Conversation version counter (story 4.2, AD-7): "cheap polls".
#
# One Redis number per Conversation: ver:<business_id>:<conversation_id>. It goes up after
# each commit that changes the Conversation. A poll that brings the same number back gets
# "no change" from Redis alone, so an idle Chat Page never wakes Postgres (AR-22).
#
# How to use: any code that changes a Conversation (a new Message now; a staff reply, a
# Handoff, a Booking in later stories) calls mark_conversation_changed(session, id). The
# number goes up only when that transaction COMMITS.
#
# The order rule (why "after commit"):
# - Up BEFORE commit: a poll could read the new number but not yet see the new row (it is
#   not committed). It stores the new number, so every later poll says "no change", and the
#   Message never shows.
# - Up AFTER commit: a poll that reads the number first, then the rows, either sees the row
#   or holds an older number. An older number differs, so the next poll reads Postgres again.
#   This needs READ COMMITTED (the Postgres default): each query sees the newest commits.
#
# Why a random start, not 1: if Redis loses a key and makes it again, a counter from 1 could
# land on the very number an old cursor holds, and that page would miss a Message. A random
# start in [2**32, 2**40) makes that match almost impossible.
#
# No expiry (TTL): the number must live as long as any page might still hold a cursor.
# In core, not inbox: bookings (Epic 5) must raise it too, and bookings cannot import inbox.
import logging
import secrets
import uuid

import redis
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.redis_client import get_redis
from app.core.tenancy import current_business_id

logger = logging.getLogger(__name__)

_PENDING = "changed_conversations"  # key in session.info: the Conversations to bump at commit
_START_LOW, _START_HIGH = 2**32, 2**40


def version_key(business_id: uuid.UUID, conversation_id: uuid.UUID) -> str:
    # Purpose first, then the Business (AD-3 key rule).
    return f"ver:{business_id}:{conversation_id}"


def _random_start() -> int:
    return _START_LOW + secrets.randbelow(_START_HIGH - _START_LOW)


def mark_conversation_changed(session: Session, conversation_id: uuid.UUID) -> None:
    """Raise this Conversation's number when the session's transaction commits."""
    # The Business is read NOW: the request's tenant scope ends before its commit.
    # A set: the same Conversation marked twice in one transaction goes up once.
    session.info.setdefault(_PENDING, set()).add((current_business_id(), conversation_id))


@event.listens_for(Session, "after_commit")
def _bump_after_commit(session: Session) -> None:
    pending = session.info.pop(_PENDING, set())
    if not pending:
        return
    try:
        with get_redis().pipeline() as pipe:
            for business_id, conversation_id in pending:
                key = version_key(business_id, conversation_id)
                pipe.set(key, _random_start(), nx=True)  # a missing key starts at a random number
                pipe.incr(key)
            pipe.execute()
    except redis.RedisError:
        # The data is already saved; failing the request now would only confuse the sender.
        # Open pages see the change with the next change or a reload.
        logger.exception("conversation version bump failed")


@event.listens_for(Session, "after_rollback")
def _forget_on_rollback(session: Session) -> None:
    session.info.pop(_PENDING, None)  # nothing was saved, so nothing changed


def read_version(business_id: uuid.UUID, conversation_id: uuid.UUID) -> int | None:
    """The number now, or None if Redis has none. For the fast poll. May raise RedisError."""
    raw = get_redis().get(version_key(business_id, conversation_id))
    return None if raw is None else int(raw)


def read_or_seed_version(business_id: uuid.UUID, conversation_id: uuid.UUID) -> int:
    """The number now; a missing one is first set to a random start. May raise RedisError.

    For the slow poll, BEFORE it reads the Messages. Seeding means a Conversation from before
    story 4.2 (or after a Redis restart) is slow for one poll only, then fast again.
    """
    key = version_key(business_id, conversation_id)
    client = get_redis()
    client.set(key, _random_start(), nx=True)
    return int(client.get(key))

# The webchat adapter: the Chat Page (/c/{slug}) as a channel (NFR-9, AD-16).
#
# A Chat Page visitor has no account. Their browser holds a random token in an httpOnly
# cookie; inbox stores only a HASH of it. Same browser = same token = same Conversation.
#
# One cookie reaches every Chat Page (a "__Host-" cookie must have Path=/), so the hash also
# mixes in the Business id. The same browser then has a DIFFERENT hash in each Business, and
# the database cannot link one visitor across Businesses.
#
# Lock order, for every flow that takes both locks: the visitor-token row FIRST, then the
# Conversation row. One fixed order means two requests can never wait for each other (deadlock).
import re
import uuid
from typing import Annotated

from fastapi import Cookie, Response
from sqlalchemy.orm import Session

from app.core.redis_client import get_redis
from app.core.tenancy import current_business_id
from app.core.tokens import hash_token
from app.modules.inbox.models import Conversation, Customer
from app.modules.inbox.repository import ConversationRepository, CustomerRepository, VisitorTokenRepository

# "__Host-": the browser accepts this cookie only if it is Secure, has Path=/ and no Domain.
VISITOR_COOKIE = "__Host-sevadesk_visitor"
VISITOR_MAX_AGE_SECONDS = 365 * 24 * 60 * 60  # a Customer may come back months later

# What new_token() makes: 43 URL-safe characters. Anything else is not our cookie.
_TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_-]{43}")

# Use in a route: `cookie: VisitorTokenCookie = None` reads the cookie (None if missing).
VisitorTokenCookie = Annotated[str | None, Cookie(alias=VISITOR_COOKIE)]


# The fast-poll map (story 4.2): one Redis entry per browser per Business. A day is plenty:
# an open Chat Page polls every 5 s, and each slow poll writes the entry again.
_MAP_SECONDS = 24 * 60 * 60


def _map_key(business_id: uuid.UUID, token_hash: str) -> str:
    return f"chat_visitor:{business_id}:{token_hash}"  # purpose, then the Business (AD-3)


def usable_token(raw: str | None) -> str | None:
    """The cookie's token, or None if it is missing or not shaped like one of ours."""
    return raw if raw is not None and _TOKEN_SHAPE.fullmatch(raw) else None


def set_visitor_cookie(response: Response, token: str) -> None:
    # httponly: page JavaScript cannot read it. secure: https only. samesite=lax: other
    # sites cannot make the browser send it on their POSTs. (The same flags as the session cookie.)
    response.set_cookie(
        VISITOR_COOKIE,
        token,
        max_age=VISITOR_MAX_AGE_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


class WebchatChannel:
    """The Chat Page visitor with this cookie token, inside the current Business."""

    def __init__(self, token: str):
        self._token = token

    def _hash(self, business_id: uuid.UUID | None = None) -> str:
        return hash_token(f"{business_id or current_business_id()}:{self._token}")

    def find_conversation(self, session: Session) -> Conversation | None:
        visitor = VisitorTokenRepository(session).find(self._hash())
        if visitor is None:
            return None  # a browser that has not sent anything yet: no rows, and none made
        return ConversationRepository(session).newest_for_visitor(visitor.id, lock=False)

    def remember_conversation(self, slug: str, conversation_id: uuid.UUID) -> None:
        """Note in Redis: this browser, on this slug, has this Conversation (for the fast poll).

        Only the slow poll calls this, inside the slug's own tenant scope, after it found the
        Conversation in Postgres by the cookie. So an entry is proof: a fast poll that finds it
        knows the Business and the Conversation without Postgres (story 4.2). May raise RedisError.
        """
        get_redis().set(_map_key(current_business_id(), self._hash()), f"{slug} {conversation_id}", ex=_MAP_SECONDS)

    def cached_conversation(self, business_id: uuid.UUID, slug: str) -> uuid.UUID | None:
        """The fast poll's lookup: this browser's Conversation in that Business, via that slug.

        No tenant scope needed: the cursor names the Business. That is only a claim, so it
        counts only if the slow poll of THIS slug wrote the entry (the slug must match).
        None for a miss or a bad value. May raise RedisError.
        """
        value = get_redis().get(_map_key(business_id, self._hash(business_id)))
        if value is None:
            return None
        saved_slug, _, raw_id = value.decode().partition(" ")
        if saved_slug != slug:
            return None  # the cookie is shared by every slug: B's entry is not proof for A
        try:
            return uuid.UUID(raw_id)
        except ValueError:
            return None

    def open_conversation(self, session: Session) -> Conversation:
        tokens, conversations = VisitorTokenRepository(session), ConversationRepository(session)
        token_hash = self._hash()
        tokens.ensure(token_hash)
        # Lock 1: this browser's row. Two first sends (a double tap) now run one after the
        # other, so the second one finds the Conversation the first one made.
        visitor = tokens.lock(token_hash)
        # Lock 2: the Conversation row, in the same query that reads it (fresh values).
        conversation = conversations.newest_for_visitor(visitor.id, lock=True)
        if conversation is None:
            # A new chat. A row this transaction inserts is already its own until commit.
            customer = CustomerRepository(session).add(Customer())
            conversation = conversations.add(Conversation(customer_id=customer.id, visitor_token_id=visitor.id))
        return conversation

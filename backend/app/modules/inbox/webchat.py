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
from typing import Annotated

from fastapi import Cookie, Response
from sqlalchemy.orm import Session

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

    def _hash(self) -> str:
        return hash_token(f"{current_business_id()}:{self._token}")

    def find_conversation(self, session: Session) -> Conversation | None:
        visitor = VisitorTokenRepository(session).find(self._hash())
        if visitor is None:
            return None  # a browser that has not sent anything yet: no rows, and none made
        return ConversationRepository(session).newest_for_visitor(visitor.id, lock=False)

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

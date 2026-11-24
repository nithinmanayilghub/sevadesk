# HTTP routes of the inbox module (story 4.1, FR-15).
# - GET  /api/v1/chat/{chat_slug}/messages?cursor=…: the poll (story 4.2, AD-7). Only the
#   Messages after the cursor, a snapshot, and a new cursor.
# - POST /api/v1/chat/{chat_slug}/messages: send one Message.
#
# Both are public: no ActorDep. The slug picks the Business (ChatBusinessDep, AD-3 b) and the
# visitor cookie picks the chat (AD-16). Neither takes a conversation_id (AR-10).
from typing import Annotated

import redis
from fastapi import APIRouter, Query, Request, Response

from app.core.client_ip import client_ip
from app.core.db import SessionDep
from app.core.errors import ErrorEnvelope
from app.core.tokens import new_token
from app.modules.business.dependencies import ChatBusinessDep, chat_business_scope
from app.modules.inbox import service
from app.modules.inbox.schemas import ChatCursor, ChatPollOut, MessageOut, SendMessageIn
from app.modules.inbox.webchat import VisitorTokenCookie, WebchatChannel, set_visitor_cookie, usable_token

router = APIRouter(prefix="/api/v1")

# Listed so the OpenAPI schema (and so the frontend types) know the error shape.
_ERROR = {"model": ErrorEnvelope}


def _visitor_token(cookie: str | None, response: Response) -> str:
    """The browser's token. A first visit (or a cookie we did not make) gets a new one.

    Only the cookie is set here, never a database row: a GET must not change data (AD-5).
    The visitor_tokens row is written by the first send.
    """
    token = usable_token(cookie)
    if token is None:
        token = new_token()
        set_visitor_cookie(response, token)
    return token


@router.get(
    "/chat/{chat_slug}/messages",
    operation_id="list_chat_messages",
    responses={404: _ERROR, 503: _ERROR},
)
def list_chat_messages(
    chat_slug: str,
    response: Response,
    session: SessionDep,
    cookie: VisitorTokenCookie = None,
    cursor: Annotated[str | None, Query(max_length=128)] = None,
) -> ChatPollOut:
    # No ChatBusinessDep here: a dependency would query Postgres before this code runs.
    # SessionDep is lazy: it opens no database connection until the first query.
    parsed = ChatCursor.parse(cursor)  # None for no cursor, or one we did not make
    token = _visitor_token(cookie, response)
    channel = WebchatChannel(token)
    with chat_business_scope(session, chat_slug) as business:
        # A cursor from another Business (the cookie is shared by every slug) starts at 0.
        after_seq = parsed.after_seq if parsed and parsed.business_id == business.business_id else 0
        answer, conversation_id = service.poll_messages(session, channel, after_seq)
        if conversation_id is not None:
            try:
                channel.remember_conversation(chat_slug.lower(), conversation_id)
            except redis.RedisError as error:
                raise service.chat_unavailable() from error
    return answer


@router.post(
    "/chat/{chat_slug}/messages",
    status_code=201,
    operation_id="send_chat_message",
    responses={404: _ERROR, 422: _ERROR, 429: _ERROR, 503: _ERROR},
)
def send_chat_message(
    body: SendMessageIn,
    request: Request,
    response: Response,
    session: SessionDep,
    business: ChatBusinessDep,
    cookie: VisitorTokenCookie = None,
) -> MessageOut:
    # Count per IP first, before any database work (the IP is an HTTP fact, so it is counted here).
    wait = service.chat_send_ip_limiter().hit(f"{business.business_id}:{client_ip(request)}")
    if wait is not None:
        raise service.TooManyMessages(retry_after=wait)
    token = _visitor_token(cookie, response)
    # Set the cookie again on each send, so a regular Customer's 365 days start again.
    # Only a send does this: a GET still changes nothing it does not have to.
    set_visitor_cookie(response, token)
    return service.receive_message(session, WebchatChannel(token), body)

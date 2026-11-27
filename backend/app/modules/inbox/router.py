# HTTP routes of the inbox module (story 4.1, FR-15).
# - GET  /api/v1/chat/{chat_slug}/messages?cursor=…: the poll (story 4.2, AD-7). Only the
#   Messages after the cursor, a snapshot, and a new cursor.
# - POST /api/v1/chat/{chat_slug}/messages: send one Message.
#
# Both are public: no ActorDep. The slug picks the Business (AD-3 b) and the visitor cookie
# picks the chat (AD-16). Neither takes a conversation_id (AR-10).
#
# The poll's fast and slow paths live in chat_poll.py. This file only reads the HTTP facts.
#
# Logged-in Inbox routes (story 4.3), for Owner and Staff (the Role check is in service.py):
# - GET /api/v1/inbox/conversations?cursor=…&limit=…: one page of the Inbox list (FR-23).
# - GET /api/v1/inbox/needs-human-count: the red number on the Inbox tab (UX-DR16).
# Both count against one per-member poll limit (AD-7) before any of their own queries.
#
# One open Conversation (story 4.4, FR-21, FR-24). An id from another Business is a 404.
# - GET  /api/v1/inbox/conversations/{id}/messages?cursor=…: the thread poll (counted too).
# - POST /api/v1/inbox/conversations/{id}/messages: a team reply; it starts a Handoff.
# - POST /api/v1/inbox/conversations/{id}/take-over and …/give-back: the Handoff bar.
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.core.client_ip import client_ip
from app.core.db import SessionDep
from app.core.errors import ErrorEnvelope
from app.core.tokens import new_token
from app.modules.accounts.dependencies import ActorDep
from app.modules.business.dependencies import ChatBusinessDep
from app.modules.inbox import chat_poll, service
from app.modules.inbox.schemas import (
    ChatPollOut,
    ConversationStateOut,
    InboxPage,
    MessageOut,
    NeedsHumanCount,
    SendMessageIn,
)
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
    responses={404: _ERROR, 429: _ERROR, 503: _ERROR},
)
def list_chat_messages(
    chat_slug: str,
    request: Request,
    response: Response,
    session: SessionDep,
    cookie: VisitorTokenCookie = None,
    cursor: Annotated[str | None, Query(max_length=128)] = None,
) -> ChatPollOut:
    # No ChatBusinessDep here: a dependency would query Postgres before this code runs.
    # SessionDep is lazy: it opens no database connection until the first query.
    token = usable_token(cookie)
    if token is None:
        # A first visit gets its cookie now. It has no chat yet, so the poll needs no token.
        set_visitor_cookie(response, new_token())
    return chat_poll.poll_chat(session, chat_slug, token, cursor, client_ip(request))


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


@router.get(
    "/inbox/conversations",
    operation_id="list_inbox_conversations",
    responses={401: _ERROR, 403: _ERROR, 422: _ERROR, 429: _ERROR, 503: _ERROR},
)
def list_inbox_conversations(
    session: SessionDep,
    actor: ActorDep,
    cursor: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = service.INBOX_PAGE_SIZE,
) -> InboxPage:
    service.count_inbox_poll(actor)  # the poll limit first, before the service's queries
    return service.list_inbox(session, actor, cursor, limit)


@router.get(
    "/inbox/needs-human-count",
    operation_id="count_needs_human",
    responses={401: _ERROR, 403: _ERROR, 429: _ERROR, 503: _ERROR},
)
def count_needs_human(session: SessionDep, actor: ActorDep) -> NeedsHumanCount:
    service.count_inbox_poll(actor)
    return service.count_needs_human(session, actor)


@router.get(
    "/inbox/conversations/{conversation_id}/messages",
    operation_id="poll_inbox_conversation",
    responses={401: _ERROR, 403: _ERROR, 404: _ERROR, 422: _ERROR, 429: _ERROR, 503: _ERROR},
)
def poll_inbox_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    actor: ActorDep,
    cursor: Annotated[str | None, Query(max_length=128)] = None,
) -> ChatPollOut:
    service.count_inbox_poll(actor)  # the poll limit first, before the service's queries
    return service.poll_for_member(session, actor, conversation_id, cursor)


@router.post(
    "/inbox/conversations/{conversation_id}/messages",
    status_code=201,
    operation_id="send_inbox_reply",
    responses={401: _ERROR, 403: _ERROR, 404: _ERROR, 422: _ERROR},
)
def send_inbox_reply(
    conversation_id: uuid.UUID, body: SendMessageIn, session: SessionDep, actor: ActorDep
) -> MessageOut:
    return service.reply(session, actor, conversation_id, body)


@router.post(
    "/inbox/conversations/{conversation_id}/take-over",
    operation_id="take_over_conversation",
    responses={401: _ERROR, 403: _ERROR, 404: _ERROR, 422: _ERROR},
)
def take_over_conversation(conversation_id: uuid.UUID, session: SessionDep, actor: ActorDep) -> ConversationStateOut:
    return service.take_over(session, actor, conversation_id)


@router.post(
    "/inbox/conversations/{conversation_id}/give-back",
    operation_id="give_back_conversation",
    responses={401: _ERROR, 403: _ERROR, 404: _ERROR, 422: _ERROR},
)
def give_back_conversation(conversation_id: uuid.UUID, session: SessionDep, actor: ActorDep) -> ConversationStateOut:
    return service.give_back(session, actor, conversation_id)

# Tables owned by the inbox module (story 4.1, AR-1). All four are tenant tables:
# each row belongs to one Business (AD-3).
# - customers: a person who chats with or phones the Business. Name and phone: story 5.2.
# - visitor_tokens: a Chat Page browser, known only by the HASH of its cookie (AD-16).
# - conversations: one chat thread, with its state and the last seq used (AD-7, AD-10).
# - messages: what was said, in order (seq), in the shape of AD-8.
#
# How they link: a Conversation points at its Customer AND at the visitor token that started
# it. So "this browser's chat" = the newest Conversation of its visitor token.
#
# Every link between them is a COMPOSITE foreign key (business_id, x_id): the database itself
# refuses a row in one Business that points at a row in another (AD-3 second guard).
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
    literal_column,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.repository import TenantModel

# The AD-8 author types and AD-10 Conversation states, in one place for models and migration.
AUTHOR_TYPES = ("customer", "agent", "user", "system")
CONVERSATION_STATES = ("agent", "handoff", "closed")
LANGS = ("en", "hi")


def _in(column: str, values: tuple[str, ...]) -> str:
    """SQL text for a CHECK rule: column IN ('a','b')."""
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class Customer(TenantModel):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),
        # A Customer is known by phone inside one Business (PRD Glossary): a phone-in Booking
        # finds the same Customer again (story 5.2). NULL phones (chat Customers) never clash.
        UniqueConstraint("business_id", "phone"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    # Personal data (AD-13): never in logs or traces. Both are empty for chat Customers until
    # the Agent collects them (Epic 6). The phone is always stored as "+91" + 10 digits.
    name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VisitorToken(TenantModel):
    """One Chat Page browser in one Business. Only the hash is kept, never the cookie value."""

    __tablename__ = "visitor_tokens"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),
        # One row per browser per Business. The same browser in another Business has another hash.
        UniqueConstraint("business_id", "token_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    token_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(TenantModel):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),
        ForeignKeyConstraint(["business_id", "customer_id"], ["customers.business_id", "customers.id"]),
        ForeignKeyConstraint(["business_id", "visitor_token_id"], ["visitor_tokens.business_id", "visitor_tokens.id"]),
        CheckConstraint(_in("state", CONVERSATION_STATES), name="state_valid"),
        CheckConstraint("last_seq >= 0", name="last_seq_valid"),
        # "This browser's newest chat" is looked up on every Chat Page load.
        Index("ix_conversations_visitor_token_id", "business_id", "visitor_token_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    customer_id: Mapped[uuid.UUID]
    visitor_token_id: Mapped[uuid.UUID]
    # Only inbox changes the state (AD-10). A new chat starts with the Agent.
    state: Mapped[str] = mapped_column(Text, server_default="agent")
    # The seq of the newest Message. The next Message gets last_seq + 1, set while this
    # row is locked, so two Messages never get the same number (AD-7).
    last_seq: Mapped[int] = mapped_column(server_default="0")
    # When the newest Message arrived: the Inbox sorts by it (story 4.3). A copy of a fact that
    # lives on the messages (a "denormalized" column), so the sort never scans all Messages.
    # Set by every new Message: the customer now; user and agent replies (4.4, Epic 6) must too.
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# "Needs Human first" (story 4.3): true for a handoff Conversation. One expression for the
# index below AND every Inbox query (sort, page, count). 'handoff' is written as fixed SQL text,
# not sent as a parameter: Postgres matches a query to an expression index only when the query
# says the same thing, and "state = $1" (a prepared query's parameter) is not "state = 'handoff'".
PINNED = Conversation.state == literal_column("'handoff'")

# The Inbox order: Needs Human first, then newest activity, then id as a tie-breaker. One index
# serves the list, its pages (keyset cursor), and the count. Migration 0010 creates it.
Index(
    "ix_conversations_inbox_order",
    Conversation.business_id,
    PINNED.self_group().desc(),  # self_group: the brackets an index expression needs
    Conversation.last_message_at.desc(),
    Conversation.id.desc(),
)


class Message(TenantModel):
    """One Message, in the AD-8 shape."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),
        UniqueConstraint("business_id", "conversation_id", "seq"),  # one Message per number
        # Idempotent send: the same client_message_id is saved once. NULLs (Agent rows) never clash.
        UniqueConstraint("business_id", "conversation_id", "client_message_id"),
        ForeignKeyConstraint(["business_id", "conversation_id"], ["conversations.business_id", "conversations.id"]),
        # A team member's reply points at their membership, in the SAME Business.
        ForeignKeyConstraint(["business_id", "author_membership_id"], ["memberships.business_id", "memberships.id"]),
        CheckConstraint(_in("author_type", AUTHOR_TYPES), name="author_type_valid"),
        # A member is named exactly when a User (team member) wrote it.
        CheckConstraint("(author_type = 'user') = (author_membership_id IS NOT NULL)", name="member_only_for_user"),
        CheckConstraint(_in("lang", LANGS), name="lang_valid"),
        CheckConstraint("char_length(body) > 0", name="body_not_empty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    conversation_id: Mapped[uuid.UUID]
    seq: Mapped[int]  # 1, 2, 3, … inside one Conversation
    author_type: Mapped[str] = mapped_column(Text)
    author_membership_id: Mapped[uuid.UUID | None]
    body: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(Text)
    client_message_id: Mapped[uuid.UUID | None]  # made by the browser; None for Agent rows
    # UI chips (AD-8), e.g. "Accept ₹499". Empty for now; the Agent stories fill it.
    actions: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

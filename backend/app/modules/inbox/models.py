# Tables owned by the inbox module (story 4.1, AR-1). All four are tenant tables:
# each row belongs to one Business (AD-3).
# - customers: a person who chats with the Business. Name and phone come in a later story.
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

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Text, UniqueConstraint, func
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
    __table_args__ = (UniqueConstraint("business_id", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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

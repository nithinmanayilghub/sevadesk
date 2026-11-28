# Database access for inbox. Only inbox's own files use it (AD-2).
#
# Every locked read also sets populate_existing=True. Why: SQLAlchemy keeps one in-memory copy
# per row it has already read in this session (the "identity map"). A second SELECT of the same
# row normally hands back that OLD copy. After waiting for a lock, we must see the NEW values
# (for example a last_seq another request just raised), so we ask SQLAlchemy to refresh the copy.
import uuid
from typing import NamedTuple

from sqlalchemy import Select, and_, func, literal, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from app.core.repository import TenantRepository
from app.core.tenancy import current_business_id
from app.modules.inbox.models import PINNED, Conversation, Customer, Message, VisitorToken
from app.modules.inbox.schemas import InboxCursor


class CustomerCounts(NamedTuple):
    """A Customer's data size, by name, so a caller cannot mix up the two numbers."""

    conversations: int
    messages: int


def _locked[T](query: Select[T]) -> Select[T]:
    # FOR UPDATE: other transactions wait for this row until ours ends. Refresh the copy too.
    return query.with_for_update().execution_options(populate_existing=True)


class CustomerRepository(TenantRepository[Customer]):
    model = Customer

    def lock(self, customer_id: uuid.UUID) -> Customer | None:
        """This Business's Customer, LOCKED (story 4.5), or None (missing or another Business's).

        Only the delete locks a Customer row, so two deletes of one Customer go in line.
        """
        return self.session.scalars(_locked(self._select().where(Customer.id == customer_id))).one_or_none()

    def find_by_phone(self, phone: str) -> Customer | None:
        """This Business's Customer with this phone (already normalized: "+91" + 10 digits)."""
        return self.session.scalars(self._select().where(Customer.phone == phone)).one_or_none()


class VisitorTokenRepository(TenantRepository[VisitorToken]):
    model = VisitorToken

    def find(self, token_hash: str) -> VisitorToken | None:
        return self.session.scalars(self._select().where(VisitorToken.token_hash == token_hash)).one_or_none()

    def ensure(self, token_hash: str) -> None:
        """Insert this browser's row if it is not there yet.

        INSERT … ON CONFLICT DO NOTHING: if two first sends arrive at once, the second insert
        waits for the first, then does nothing (no IntegrityError, no 500). The tenant filter is
        written by hand here, because the base class only builds SELECTs and add() (like
        WorkingHoursRepository.replace_week).
        """
        statement = (
            insert(VisitorToken)
            .values(id=uuid.uuid7(), business_id=current_business_id(), token_hash=token_hash)
            .on_conflict_do_nothing(index_elements=["business_id", "token_hash"])
        )
        self.session.execute(statement)

    def ensure_and_lock(self, token_hash: str) -> VisitorToken:
        """This browser's row, made if needed and LOCKED: its sends now wait in line, one at a time.

        A Customer delete (story 4.5) can hold this row's lock and then delete the row. A send
        that waited for that lock then finds NO row (under READ COMMITTED, a locked read skips a
        row deleted meanwhile). So we make the row once more: this browser starts fresh, as a
        new Customer. The second row is our own and not committed yet, so no one can delete it.
        """
        query = _locked(self._select().where(VisitorToken.token_hash == token_hash))
        self.ensure(token_hash)
        row = self.session.scalars(query).one_or_none()
        if row is None:
            # A delete removed the row while we waited for its lock: make it again.
            self.ensure(token_hash)
            row = self.session.scalars(query).one()
        return row

    def lock_ids(self, ids: list[uuid.UUID]) -> None:
        """Lock these rows (story 4.5). In id order, so two callers always lock in the same order."""
        self.session.scalars(_locked(self._select().where(VisitorToken.id.in_(ids)).order_by(VisitorToken.id))).all()


class ConversationRepository(TenantRepository[Conversation]):
    model = Conversation

    def newest_for_visitor(self, visitor_token_id: uuid.UUID, *, lock: bool) -> Conversation | None:
        """The visitor's newest Conversation, in ONE query (locked if lock=True)."""
        query = (
            self._select()
            .where(Conversation.visitor_token_id == visitor_token_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(1)
        )
        return self.session.scalars(_locked(query) if lock else query).one_or_none()

    def lock(self, conversation_id: uuid.UUID) -> Conversation | None:
        """This Business's Conversation with this id, LOCKED (story 4.4), or None.

        Another Business's id gives None, like a missing one: the tenant filter hides it.
        """
        return self.session.scalars(_locked(self._select().where(Conversation.id == conversation_id))).one_or_none()

    def visitor_token_ids_of(self, customer_id: uuid.UUID) -> list[uuid.UUID]:
        """The visitor tokens this Customer's Conversations point at (no lock: these ids never change)."""
        # Starts from _select(), so the tenant filter comes from the one place that adds it (AD-3).
        query = (
            self._select()
            .where(Conversation.customer_id == customer_id)
            .with_only_columns(Conversation.visitor_token_id, maintain_column_froms=True)
            .distinct()
        )
        return list(self.session.scalars(query))

    def lock_for_customer(self, customer_id: uuid.UUID) -> list[uuid.UUID]:
        """Lock this Customer's Conversations, in id order. Returns their ids."""
        query = _locked(self._select().where(Conversation.customer_id == customer_id).order_by(Conversation.id))
        return [conversation.id for conversation in self.session.scalars(query)]

    def count_for_customer(self, customer_id: uuid.UUID) -> CustomerCounts:
        """How many Conversations and Messages this Customer has, for the Customer detail sheet."""
        # Starts from _select() (the tenant filter, AD-3). The join also matches business_id.
        # count(DISTINCT id): each Conversation is counted once, however many Messages it has.
        query = (
            self._select()
            .where(Conversation.customer_id == customer_id)
            .outerjoin(
                Message,
                and_(Message.business_id == Conversation.business_id, Message.conversation_id == Conversation.id),
            )
            .with_only_columns(
                func.count(func.distinct(Conversation.id)), func.count(Message.id), maintain_column_froms=True
            )
        )
        conversations, messages = self.session.execute(query).one()
        return CustomerCounts(conversations=conversations, messages=messages)

    def inbox_page(self, after: InboxCursor | None, limit: int) -> list[tuple[Conversation, Message]]:
        """Up to limit + 1 Conversations with their newest Message, in the Inbox order (story 4.3).

        It reads two tenant tables in one JOIN, so it writes the tenant filter by hand: the
        base class filters one model only. The join itself also matches business_id.

        The extra row is not shown: it only tells the caller "there is a next page".
        The newest Message is the one with seq = last_seq; (business_id, conversation_id, seq)
        is unique, so the join finds exactly one, through that unique index.
        """
        business_id = current_business_id()
        query = (
            select(Conversation, Message)
            .join(
                Message,
                and_(
                    Message.business_id == Conversation.business_id,
                    Message.conversation_id == Conversation.id,
                    Message.seq == Conversation.last_seq,
                ),
            )
            .where(Conversation.business_id == business_id)
            .order_by(PINNED.desc(), Conversation.last_message_at.desc(), Conversation.id.desc())
            .limit(limit + 1)
        )
        if after is not None:
            # Row compare: "comes after the cursor row in this order". Every part sorts DESC,
            # so "after" means "less than" for the whole row (false < true for PINNED).
            sort_key = tuple_(PINNED.self_group(), Conversation.last_message_at, Conversation.id)
            query = query.where(sort_key < tuple_(literal(after.pinned), after.last_message_at, after.conversation_id))
        return [(conversation, message) for conversation, message in self.session.execute(query)]

    def count_needs_human(self) -> int:
        """How many of this Business's Conversations are in Handoff. Uses the Inbox index."""
        # Starts from _select(), so the tenant filter comes from the one place that adds it
        # (AD-3); with_only_columns swaps the selected rows for count(*), FROM and WHERE stay.
        query = self._select().where(PINNED).with_only_columns(func.count(), maintain_column_froms=True)
        return self.session.scalar(query)


class MessageRepository(TenantRepository[Message]):
    model = Message

    def list_after(self, conversation_id: uuid.UUID, after_seq: int) -> list[Message]:
        """The Messages with seq > after_seq, oldest first (after_seq=0: all of them)."""
        query = (
            self._select()
            .where(Message.conversation_id == conversation_id, Message.seq > after_seq)
            .order_by(Message.seq)
        )
        return list(self.session.scalars(query))

    def find_by_client_id(self, conversation_id: uuid.UUID, client_message_id: uuid.UUID) -> Message | None:
        query = self._select().where(
            Message.conversation_id == conversation_id, Message.client_message_id == client_message_id
        )
        return self.session.scalars(query).one_or_none()

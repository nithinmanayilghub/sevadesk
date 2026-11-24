# Database access for inbox. Only inbox's own files use it (AD-2).
#
# Every locked read also sets populate_existing=True. Why: SQLAlchemy keeps one in-memory copy
# per row it has already read in this session (the "identity map"). A second SELECT of the same
# row normally hands back that OLD copy. After waiting for a lock, we must see the NEW values
# (for example a last_seq another request just raised), so we ask SQLAlchemy to refresh the copy.
import uuid

from sqlalchemy import Select
from sqlalchemy.dialects.postgresql import insert

from app.core.repository import TenantRepository
from app.core.tenancy import current_business_id
from app.modules.inbox.models import Conversation, Customer, Message, VisitorToken


def _locked[T](query: Select[T]) -> Select[T]:
    # FOR UPDATE: other transactions wait for this row until ours ends. Refresh the copy too.
    return query.with_for_update().execution_options(populate_existing=True)


class CustomerRepository(TenantRepository[Customer]):
    model = Customer


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

    def lock(self, token_hash: str) -> VisitorToken:
        """This browser's row, locked: its sends now wait in line, one at a time."""
        return self.session.scalars(_locked(self._select().where(VisitorToken.token_hash == token_hash))).one()


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

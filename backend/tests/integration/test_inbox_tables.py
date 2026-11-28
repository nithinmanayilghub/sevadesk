# Database guards for the inbox tables (story 4.1, AR-1, AR-12, AR-13). These tests write rows
# directly, past the API, to prove the database ITSELF refuses bad data.
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.integration.conftest import membership_of

from app.core.db import get_engine
from app.modules.inbox.models import Conversation, Customer, Message, VisitorToken


def insert(*rows) -> None:
    """Save rows in their OWN session: a failed INSERT spoils a session until rollback."""
    with Session(get_engine()) as session, session.begin():
        session.add_all(rows)


def new_conversation(business_id: uuid.UUID) -> uuid.UUID:
    """A Customer, a visitor token, and a Conversation in this Business. Returns the Conversation id."""
    # Ids made here, not read back from the rows: a commit expires the rows' values.
    customer_id, token_id, conversation_id = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    insert(
        Customer(id=customer_id, business_id=business_id),
        VisitorToken(id=token_id, business_id=business_id, token_hash=uuid.uuid4().hex),
    )
    conversation = Conversation(
        id=conversation_id, business_id=business_id, customer_id=customer_id, visitor_token_id=token_id
    )
    insert(conversation)
    return conversation_id


def message(business_id: uuid.UUID, conversation_id: uuid.UUID, seq: int, **fields) -> Message:
    values = {"author_type": "customer", "body": "Hello", "lang": "en", "client_message_id": uuid.uuid4()}
    return Message(business_id=business_id, conversation_id=conversation_id, seq=seq, **(values | fields))


def test_new_conversation_starts_in_agent_state_at_seq_zero(sign_up_owner):
    _, business_id = sign_up_owner()
    conversation_id = new_conversation(business_id)
    with Session(get_engine()) as session:
        row = session.get(Conversation, conversation_id)
        assert (row.state, row.last_seq) == ("agent", 0)


def test_seq_is_unique_per_conversation(sign_up_owner):
    _, business_id = sign_up_owner()
    conversation_id = new_conversation(business_id)
    insert(message(business_id, conversation_id, 1))
    with pytest.raises(IntegrityError, match="uq_messages_business_id_conversation_id_seq"):
        insert(message(business_id, conversation_id, 1))


def test_client_message_id_is_unique_per_conversation(sign_up_owner):
    _, business_id = sign_up_owner()
    conversation_id = new_conversation(business_id)
    client_id = uuid.uuid4()
    insert(message(business_id, conversation_id, 1, client_message_id=client_id))
    with pytest.raises(IntegrityError, match="uq_messages_business_id_conversation_id_client_message_id"):
        insert(message(business_id, conversation_id, 2, client_message_id=client_id))


def test_two_null_client_message_ids_are_allowed(sign_up_owner):
    # Agent Messages have no client_message_id. NULLs never clash in a UNIQUE rule.
    _, business_id = sign_up_owner()
    conversation_id = new_conversation(business_id)
    insert(
        message(business_id, conversation_id, 1, author_type="agent", client_message_id=None),
        message(business_id, conversation_id, 2, author_type="agent", client_message_id=None),
    )


def test_bad_author_type_is_refused(sign_up_owner):
    _, business_id = sign_up_owner()
    conversation_id = new_conversation(business_id)
    with pytest.raises(IntegrityError, match="ck_messages_author_type_valid"):
        insert(message(business_id, conversation_id, 1, author_type="robot"))


def test_user_message_needs_a_member(sign_up_owner):
    _, business_id = sign_up_owner()
    conversation_id = new_conversation(business_id)
    with pytest.raises(IntegrityError, match="ck_messages_member_only_for_user"):
        insert(message(business_id, conversation_id, 1, author_type="user", client_message_id=None))
    with pytest.raises(IntegrityError, match="ck_messages_member_only_for_user"):
        insert(message(business_id, conversation_id, 1, author_membership_id=membership_of(business_id)))
    # A user Message WITH its member is fine.
    insert(
        message(
            business_id,
            conversation_id,
            1,
            author_type="user",
            client_message_id=None,
            author_membership_id=membership_of(business_id),
        )
    )


def test_bad_lang_and_empty_body_are_refused(sign_up_owner):
    _, business_id = sign_up_owner()
    conversation_id = new_conversation(business_id)
    with pytest.raises(IntegrityError, match="ck_messages_lang_valid"):
        insert(message(business_id, conversation_id, 1, lang="fr"))
    with pytest.raises(IntegrityError, match="ck_messages_body_not_empty"):
        insert(message(business_id, conversation_id, 1, body=""))


def test_message_cannot_point_into_another_business(sign_up_owner):
    # The composite foreign key (business_id, conversation_id): A's row cannot use B's Conversation.
    _, a = sign_up_owner()
    _, b = sign_up_owner()
    b_conversation = new_conversation(b)
    with pytest.raises(IntegrityError, match="fk_messages_business_id_conversations"):
        insert(message(a, b_conversation, 1))


def test_phone_is_unique_per_business(sign_up_owner):
    # Story 5.2: a Customer is known by phone inside ONE Business (PRD Glossary).
    _, a = sign_up_owner()
    _, b = sign_up_owner()
    phone = "+919876543210"
    # The same phone in two Businesses: two different Customers, both fine.
    insert(Customer(business_id=a, phone=phone), Customer(business_id=b, phone=phone))
    # Chat Customers have no phone yet: two NULL phones never clash.
    insert(Customer(business_id=a), Customer(business_id=a))
    with pytest.raises(IntegrityError, match="uq_customers_business_id_phone"):
        insert(Customer(business_id=a, phone=phone, name="Someone else"))


def test_visitor_token_hash_unique_per_business(sign_up_owner):
    _, a = sign_up_owner()
    _, b = sign_up_owner()
    insert(VisitorToken(business_id=a, token_hash="same"), VisitorToken(business_id=b, token_hash="same"))
    with pytest.raises(IntegrityError, match="uq_visitor_tokens_business_id_token_hash"):
        insert(VisitorToken(business_id=a, token_hash="same"))

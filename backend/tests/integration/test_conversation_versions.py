# The Conversation version counter (story 4.2, AD-7): a Redis number that goes up AFTER each
# commit that changes a Conversation. Polls compare it with their cursor to skip Postgres.
import logging
import uuid

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.test_chat_messages import post

from app.core import versions
from app.core.db import get_engine
from app.core.redis_client import get_redis
from app.core.tenancy import tenant_scope
from app.core.versions import mark_conversation_changed, version_key
from app.modules.inbox import service
from app.modules.inbox.models import Conversation

START = 2**32  # the lowest random start (a counter never starts at 0 or 1)


def conversation_id(business_id: uuid.UUID) -> uuid.UUID:
    with Session(get_engine()) as session:
        return session.scalars(select(Conversation.id).where(Conversation.business_id == business_id)).one()


def version(business_id: uuid.UUID) -> int | None:
    raw = get_redis().get(version_key(business_id, conversation_id(business_id)))
    return None if raw is None else int(raw)


def test_send_bumps_version_after_commit(client, shop):
    assert post(client, shop.slug).status_code == 201
    first = version(shop.business_id)
    assert first is not None and first >= START
    assert post(client, shop.slug).status_code == 201
    assert version(shop.business_id) == first + 1


def test_duplicate_send_does_not_bump(client, shop):
    same = uuid.uuid4()
    post(client, shop.slug, client_id=same)
    before = version(shop.business_id)
    assert post(client, shop.slug, client_id=same).status_code == 201
    assert version(shop.business_id) == before


def test_refused_send_does_not_bump(client, shop, monkeypatch):
    monkeypatch.setattr(service, "CHAT_SEND_CONVERSATION_LIMIT", 1)
    post(client, shop.slug)
    before = version(shop.business_id)
    assert post(client, shop.slug).status_code == 429
    assert version(shop.business_id) == before


def test_bump_waits_for_commit(migrated_db):
    business_id, conv_id = uuid.uuid4(), uuid.uuid4()
    key = version_key(business_id, conv_id)
    with Session(get_engine()) as session:
        session.begin()
        with tenant_scope(business_id):
            mark_conversation_changed(session, conv_id)
        assert get_redis().get(key) is None  # not yet: nothing is committed
        session.commit()
    assert get_redis().get(key) is not None


def test_rollback_drops_the_mark(migrated_db):
    business_id, conv_id = uuid.uuid4(), uuid.uuid4()
    with Session(get_engine()) as session:
        session.begin()
        with tenant_scope(business_id):
            mark_conversation_changed(session, conv_id)
        session.rollback()
        with session.begin():  # a later, empty transaction commits
            pass
    assert get_redis().get(version_key(business_id, conv_id)) is None


def test_lost_key_gets_a_new_random_start(client, shop):
    post(client, shop.slug)
    old = version(shop.business_id)
    get_redis().delete(version_key(shop.business_id, conversation_id(shop.business_id)))  # Redis lost it
    post(client, shop.slug)
    new = version(shop.business_id)
    assert new is not None and new >= START
    assert new != old + 1  # an old cursor (old + 1 after one bump) cannot match by chance


def test_bump_failure_is_logged_not_raised(client, shop, monkeypatch, caplog):
    # Only the counter's Redis is broken; the send limiter (in inbox.service) keeps the real one.
    monkeypatch.setattr(versions, "get_redis", lambda: redis.Redis.from_url("redis://127.0.0.1:1/0"))
    with caplog.at_level(logging.ERROR, logger="app.core.versions"):
        assert post(client, shop.slug).status_code == 201  # the Message is saved anyway
    assert "conversation version bump failed" in caplog.text

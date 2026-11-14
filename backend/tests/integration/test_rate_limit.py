# Integration tests for the attempt limiter (story 2.2, D3) on a real Valkey.
# "Count first": every attempt adds 1 BEFORE the expensive work, so parallel requests
# cannot all see a count of 0 and slip through.
import uuid

import pytest
import redis

from app.core.errors import AppError
from app.core.rate_limit import AttemptLimiter


@pytest.fixture
def limiter(redis_url) -> AttemptLimiter:
    return AttemptLimiter(
        redis.Redis.from_url(redis_url), "test_fail", limit=5, lock_seconds=900, unavailable_message="Down."
    )


def key() -> str:
    return uuid.uuid4().hex  # a fresh key per test, so tests never share a count


def test_limit_attempts_pass_then_the_next_is_refused(limiter):
    k = key()
    assert [limiter.hit(k) for _ in range(5)] == [None] * 5
    wait = limiter.hit(k)
    assert wait is not None and 0 < wait <= 900


def test_clear_resets_the_count(limiter):
    k = key()
    for _ in range(6):
        limiter.hit(k)
    limiter.clear(k)
    assert limiter.hit(k) is None


def test_undo_takes_one_attempt_back(limiter):
    k = key()
    for _ in range(5):
        limiter.hit(k)
    limiter.undo(k)  # count 4
    assert limiter.hit(k) is None  # count 5: still allowed
    assert limiter.hit(k) is not None  # count 6: refused


def test_key_has_the_purpose_prefix_and_an_expiry(limiter, redis_url):
    k = key()
    limiter.hit(k)
    client = redis.Redis.from_url(redis_url)
    assert client.ttl(f"test_fail:{k}") > 0  # never a key that lives forever


def test_redis_down_is_a_503():
    dead = AttemptLimiter(
        redis.Redis.from_url("redis://localhost:1/0", socket_connect_timeout=1),
        "test_fail",
        limit=5,
        lock_seconds=900,
        unavailable_message="Log-in is not available right now. Please try again.",
    )
    with pytest.raises(AppError) as error:
        dead.hit(key())
    assert error.value.status_code == 503
    assert error.value.code == "dependency_unavailable"
    assert error.value.message == "Log-in is not available right now. Please try again."

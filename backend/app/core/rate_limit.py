# The attempt limiter (story 2.2, D3): caps how many tries one key (an account, an IP)
# gets, using a counter in Redis/Valkey. Used for log-in now; for the chat page later.
#
# "Count first": hit() adds 1 BEFORE the expensive work (the password check).
# If we counted only after a failure, 10 requests sent at the same moment would all
# see a count of 0 and all get a guess.
import redis

from app.core.errors import AppError


class AttemptLimiter:
    def __init__(self, client: redis.Redis, purpose: str, limit: int, lock_seconds: int, unavailable_message: str):
        self.redis = client
        self.purpose = purpose  # first part of every key, e.g. "login_fail:acct" (AD-3 key rule)
        self.limit = limit  # attempts allowed before the lock
        self.lock_seconds = lock_seconds  # how long the lock lasts
        self.unavailable_message = unavailable_message  # shown when Redis is down

    def _name(self, key: str) -> str:
        return f"{self.purpose}:{key}"

    def _unavailable(self) -> AppError:
        # Fail closed: without the counter we cannot protect the account, so refuse (503).
        return AppError("dependency_unavailable", self.unavailable_message, 503)

    def hit(self, key: str) -> int | None:
        """Count one attempt. Return None if it is allowed, else the seconds left in the lock."""
        name = self._name(key)
        try:
            # One MULTI/EXEC transaction: the count and its expiry are written together,
            # so a crash between them cannot leave a key that never expires.
            # NX = set the expiry only if the key has none yet (the first attempt).
            with self.redis.pipeline() as pipe:
                pipe.incr(name)
                pipe.expire(name, self.lock_seconds, nx=True)
                count, _ = pipe.execute()
            if count == self.limit:
                # The limit-reaching attempt starts a fresh, fixed lock.
                self.redis.expire(name, self.lock_seconds)
            if count <= self.limit:
                return None
            seconds_left = self.redis.ttl(name)
            if seconds_left < 0:
                # No expiry found (should not happen): set one, so the lock always ends.
                self.redis.expire(name, self.lock_seconds)
                return self.lock_seconds
            return seconds_left
        except redis.RedisError as error:
            raise self._unavailable() from error

    def undo(self, key: str) -> None:
        """Take one attempt back (an attempt that turned out fine should not count)."""
        try:
            self.redis.decr(self._name(key))
        except redis.RedisError as error:
            raise self._unavailable() from error

    def clear(self, key: str) -> None:
        """Forget all attempts for this key."""
        try:
            self.redis.delete(self._name(key))
        except redis.RedisError as error:
            raise self._unavailable() from error

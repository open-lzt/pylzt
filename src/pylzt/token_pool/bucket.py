"""Token-bucket refill math — the one component that gets paranoid coverage.

A bug here means a token quietly exceeds its per-token budget and the account is
banned. The math is pure (clock-injected, no I/O) so it is exhaustively unit
tested. Each marketplace token owns one bucket per `RateClass` (`general`,
`search`, `forum`, ...) because the limit is per-token and per-class.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, PrivateAttr

from pylzt.lib.clock import Clock
from pylzt.token_pool.rate_limit import RateLimitSnapshot
from pylzt.types import RateClass


class TokenBucket(BaseModel):
    """Continuous-refill bucket. `capacity` tokens refill at `rate` per second."""

    model_config = ConfigDict(validate_assignment=False)

    capacity: float
    rate: float
    # Not constructor args (dataclass previously took them positionally, but only
    # `per_minute` ever did so) — mutable refill state, set immediately below.
    _tokens: float = PrivateAttr(default=0.0)
    _last: float = PrivateAttr(default=0.0)

    @classmethod
    def per_minute(cls, per_minute: int, clock: Clock) -> TokenBucket:
        """Build a bucket of `per_minute` capacity refilling smoothly over 60 s."""
        bucket = cls(capacity=float(per_minute), rate=per_minute / 60.0)
        bucket._tokens = float(per_minute)
        bucket._last = clock.monotonic()
        return bucket

    def _refill(self, now: float) -> None:
        elapsed = now - self._last
        if elapsed <= 0:
            return
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last = now

    def available(self, clock: Clock) -> float:
        self._refill(clock.monotonic())
        return self._tokens

    def try_consume(self, clock: Clock, amount: float = 1.0) -> bool:
        """Take `amount` tokens if present. Returns False without mutating if short."""
        self._refill(clock.monotonic())
        if self._tokens >= amount:
            self._tokens -= amount
            return True
        return False

    def time_until(self, clock: Clock, amount: float = 1.0) -> float:
        """Seconds until `amount` tokens are available (0.0 if already)."""
        self._refill(clock.monotonic())
        if self._tokens >= amount:
            return 0.0
        deficit = amount - self._tokens
        return deficit / self.rate

    def reconcile(self, remaining: int, clock: Clock) -> None:
        """Clamp local budget down to the server's ground truth. Never raises
        it — a server-reported *higher* `remaining` is ignored, only
        tightening is trusted (phase-misaligned windows make a server
        `remaining` a lower bound at best, never grounds for extra budget)."""
        self._refill(clock.monotonic())
        self._tokens = min(self._tokens, float(remaining))


class RateBucketSet(BaseModel):
    """One per-token bucket per `RateClass`, selected by a request's class.

    N-ary successor to the old two-field `DualBucket` — adding a new
    `RateClass` member is a `standard()` kwarg + dict entry, not a new field.
    """

    model_config = ConfigDict(validate_assignment=False)

    _buckets: dict[RateClass, TokenBucket] = PrivateAttr()

    @classmethod
    def standard(
        cls, clock: Clock, *, general: int = 120, search: int = 20, forum: int = 300
    ) -> RateBucketSet:
        instance = cls()
        instance._buckets = {
            RateClass.GENERAL: TokenBucket.per_minute(general, clock),
            RateClass.SEARCH: TokenBucket.per_minute(search, clock),
            RateClass.FORUM: TokenBucket.per_minute(forum, clock),
        }
        return instance

    def _select(self, rate_class: RateClass) -> TokenBucket:
        return self._buckets[rate_class]

    def try_consume(self, rate_class: RateClass, clock: Clock) -> bool:
        return self._select(rate_class).try_consume(clock)

    def time_until(self, rate_class: RateClass, clock: Clock) -> float:
        return self._select(rate_class).time_until(clock)

    def reconcile(self, rate_class: RateClass, snapshot: RateLimitSnapshot, clock: Clock) -> None:
        """Delegate to the matching bucket. Unknown `rate_class` (e.g.
        `ANTIPUBLIC`, which never reaches this pool) is a defensive no-op."""
        try:
            bucket = self._select(rate_class)
        except KeyError:
            return
        bucket.reconcile(snapshot.remaining, clock)

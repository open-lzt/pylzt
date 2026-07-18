"""Circuit-breaker health tracker for a single proxy.

Pure state object — no asyncio, no I/O.  Used by pool implementations to
decide whether a proxy is safe to use right now.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, PrivateAttr

from pylzt.types import ProxyId, ProxyOutcome

if TYPE_CHECKING:
    from pylzt.lib.clock import Clock


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ProxyHealth(BaseModel):
    """Exponential-backoff circuit breaker for one proxy endpoint."""

    model_config = ConfigDict(validate_assignment=False)

    proxy_id: ProxyId
    base_cooldown: float = 30.0
    max_cooldown: float = 3600.0
    failure_threshold: int = 3

    # Not constructor args (dataclass `init=False` equivalent) — internal breaker
    # state, mutated only by report()/_trip()/is_available().
    _state: BreakerState = PrivateAttr(default=BreakerState.CLOSED)
    _consecutive_failures: int = PrivateAttr(default=0)
    _trip_count: int = PrivateAttr(default=0)
    _unavailable_until: float = PrivateAttr(default=0.0)

    def report(self, outcome: ProxyOutcome, clock: Clock) -> None:
        """Record the result of one request through this proxy."""
        if outcome == ProxyOutcome.OK:
            self._consecutive_failures = 0
            if self._state in (BreakerState.OPEN, BreakerState.HALF_OPEN):
                self._state = BreakerState.CLOSED
        elif outcome == ProxyOutcome.BANNED:
            self._trip(clock)
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._trip(clock)

    def _trip(self, clock: Clock) -> None:
        self._trip_count += 1
        cooldown = min(
            self.base_cooldown * (2 ** (self._trip_count - 1)),
            self.max_cooldown,
        )
        self._unavailable_until = clock.monotonic() + cooldown
        self._state = BreakerState.OPEN

    def is_available(self, clock: Clock) -> bool:
        if self._state == BreakerState.CLOSED:
            return True
        if self._state == BreakerState.OPEN:
            if clock.monotonic() >= self._unavailable_until:
                self._state = BreakerState.HALF_OPEN
                return True
            return False
        return True

    def time_until_available(self, clock: Clock) -> float:
        if self._state != BreakerState.OPEN:
            return 0.0
        return max(self._unavailable_until - clock.monotonic(), 0.0)

"""Pluggable retry policy. Decides *whether* and *how long* to wait, not *how*.

The request loop owns the actual sleep+resend; the policy is pure decision logic
so it is unit-tested without a clock or a network.
"""

from __future__ import annotations

import secrets
from abc import ABC, abstractmethod

from pylzt.errors import (
    AuthFailed,
    BadRequest,
    Forbidden,
    LztError,
    NotFound,
    RateLimited,
    RetryableUpstream,
    TransportError,
)

# Terminal errors: a retry can never succeed, so the policy stops immediately.
_TERMINAL = (AuthFailed, Forbidden, NotFound, BadRequest)


class BaseRetryPolicy(ABC):
    @abstractmethod
    def next_delay(self, attempt: int, exc: LztError) -> float | None:
        """Seconds to wait before retry `attempt`, or `None` to give up."""


class ExponentialBackoff(BaseRetryPolicy):
    """Exponential backoff with full jitter, capped, honoring `Retry-After`."""

    def __init__(
        self,
        *,
        base: float = 0.5,
        factor: float = 2.0,
        cap: float = 30.0,
        max_attempts: int = 6,
    ) -> None:
        self._base = base
        self._factor = factor
        self._cap = cap
        self._max_attempts = max_attempts

    def next_delay(self, attempt: int, exc: LztError) -> float | None:
        if attempt >= self._max_attempts:
            return None
        if isinstance(exc, _TERMINAL):
            return None
        if isinstance(exc, RateLimited) and exc.retry_after is not None:
            return min(exc.retry_after, self._cap)
        if not isinstance(exc, RateLimited | RetryableUpstream | TransportError):
            return None
        ceiling = min(self._cap, self._base * (self._factor**attempt))
        # full jitter — spread retries so a fleet does not thunder in lockstep.
        return ceiling * (secrets.randbelow(10_000) / 10_000)

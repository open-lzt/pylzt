"""Single-credential token pool for API targets that aren't fungible with the
market/forum fleet (AntiPublic's license key — see `client.py`'s antipublic wiring).

Algorithm-inspired by `RoundRobinTokenPool` (park-outside-the-lock refill wait) but
deliberately standalone: `RateBucketSet` is hardcoded to the 3 named market/forum
`RateClass` members plus a multi-token selector, neither of which fits one credential
metered under one `RateClass` (`RateClass.ANTIPUBLIC`).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pylzt.errors import AuthFailed
from pylzt.lib.clock import Clock, RealClock
from pylzt.proxy_pool.base import Proxy
from pylzt.token_pool.base import BaseTokenPool, Lease, Token
from pylzt.token_pool.bucket import TokenBucket
from pylzt.types import ProxyOutcome, RateClass, TokenId


class NoUsableCredential(RuntimeError):
    """Raised when the sole configured credential is quarantined (a `401` on
    AntiPublic — the caller must construct a fresh pool with a valid key)."""


class _StaticBearerPool(BaseTokenPool):
    """One fixed Bearer credential, metered by a single `TokenBucket`. No proxy
    binding (`Lease.proxy` is always `None` — AntiPublic has no proxy-pool story
    today), no rotation (one credential, nothing to round-robin over)."""

    def __init__(
        self, *, key: str, per_min: int = 60, clock: Clock | None = None, park_poll: float = 0.05
    ) -> None:
        self._clock = clock or RealClock()
        self._token = Token(token_id=TokenId("antipublic"), credential=key)
        self._bucket = TokenBucket.per_minute(per_min, self._clock)
        self._lock = asyncio.Lock()
        self._park_poll = park_poll
        self._quarantined = False

    def quarantine(self, token_id: TokenId) -> None:
        self._quarantined = True

    def report_proxy(self, proxy: Proxy, outcome: ProxyOutcome) -> None:
        return None

    @asynccontextmanager
    async def lease(self, rate_class: RateClass) -> AsyncIterator[Lease]:
        await self._acquire()
        try:
            yield Lease(token=self._token, proxy=None)
        except AuthFailed:
            self.quarantine(self._token.token_id)
            raise

    async def _acquire(self) -> None:
        while True:
            async with self._lock:
                if self._quarantined:
                    raise NoUsableCredential("antipublic credential quarantined")
                if self._bucket.try_consume(self._clock):
                    return
                wait = self._bucket.time_until(self._clock)
            # Slept outside the lock so other coroutines can still release budget.
            await asyncio.sleep(max(self._park_poll, min(wait, 6.0)))

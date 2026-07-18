"""Round-robin token pool: the single owner of rate-limit + sticky-proxy binding.

`lease(rate_class)` rotates over the fleet, consumes one token's class bucket
(per-token, so no token ever exceeds budget), binds that token's sticky proxy,
and yields the pair. A `401` quarantines the token (§5 token health) so a dead
token never burns the fleet budget or cascades into a `429`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from pylzt.errors import AuthFailed
from pylzt.lib.clock import Clock, RealClock
from pylzt.lib.metrics import BaseMetrics, NullMetrics
from pylzt.proxy_pool.base import BaseProxyPool, Proxy
from pylzt.proxy_pool.sticky import NullProxyPool
from pylzt.token_pool.base import BaseTokenPool, Lease, Token
from pylzt.token_pool.bucket import RateBucketSet
from pylzt.token_pool.rate_limit import RateLimitSnapshot
from pylzt.token_pool.selector import BaseTokenSelector, RoundRobinSelector
from pylzt.types import ProxyOutcome, RateClass, TokenId


class NoUsableToken(RuntimeError):
    """Raised when every configured token is quarantined or none were given."""


class RoundRobinTokenPool(BaseTokenPool):
    def __init__(
        self,
        tokens: Iterable[Token],
        *,
        proxy_pool: BaseProxyPool | None = None,
        clock: Clock | None = None,
        general_per_min: int = 120,
        search_per_min: int = 20,
        forum_per_min: int = 300,
        metrics: BaseMetrics | None = None,
        selector: BaseTokenSelector | None = None,
        park_poll: float = 0.05,
    ) -> None:
        self._tokens = list(tokens)
        if not self._tokens:
            raise NoUsableToken("token pool requires at least one token")
        self._clock = clock or RealClock()
        self._selector = selector or RoundRobinSelector()
        self._buckets: dict[TokenId, RateBucketSet] = {
            t.token_id: RateBucketSet.standard(
                self._clock,
                general=general_per_min,
                search=search_per_min,
                forum=forum_per_min,
            )
            for t in self._tokens
        }
        self._proxy_pool = proxy_pool or NullProxyPool()
        self._metrics = metrics or NullMetrics()
        self._lock = asyncio.Lock()
        self._quarantined: set[TokenId] = set()
        self._park_poll = park_poll

    def quarantine(self, token_id: TokenId) -> None:
        """Pull a token out of rotation after a `401`/repeated `403` (§5)."""
        self._quarantined.add(token_id)
        self._metrics.incr("token_quarantined", token_id=str(token_id))

    def restore(self, token_id: TokenId) -> None:
        self._quarantined.discard(token_id)

    def report_proxy(self, proxy: Proxy, outcome: ProxyOutcome) -> None:
        self._proxy_pool.report(proxy.proxy_id, outcome)

    def report_rate_limit(
        self, token_id: TokenId, rate_class: RateClass, snapshot: RateLimitSnapshot
    ) -> None:
        """Tighten the matching token's bucket. Unknown `token_id` (e.g. a
        token quarantined mid-flight, between lease and response) is a
        silent no-op — nothing left to reconcile."""
        bucket_set = self._buckets.get(token_id)
        if bucket_set is None:
            return
        bucket_set.reconcile(rate_class, snapshot, self._clock)

    @asynccontextmanager
    async def lease(self, rate_class: RateClass) -> AsyncIterator[Lease]:
        token = await self._acquire_token(rate_class)
        try:
            async with self._proxy_pool.acquire(token.token_id) as proxy:
                yield Lease(token=token, proxy=proxy)
        except AuthFailed:
            # A token that auth-fails mid-request is quarantined, then re-raised
            # so the request loop can retry on a fresh lease.
            self.quarantine(token.token_id)
            raise

    async def _acquire_token(self, rate_class: RateClass) -> Token:
        while True:
            async with self._lock:
                live = [t for t in self._tokens if t.token_id not in self._quarantined]
                if not live:
                    raise NoUsableToken("all tokens quarantined")
                for token in self._selector.candidates(live):
                    if self._buckets[token.token_id].try_consume(rate_class, self._clock):
                        self._selector.on_leased(token, live)
                        self._metrics.incr("token_leased", rate_class=rate_class.value)
                        return token
                wait = min(
                    self._buckets[t.token_id].time_until(rate_class, self._clock) for t in live
                )
            # Slept outside the lock so other coroutines can still release budget.
            self._metrics.incr("token_pool_parked", rate_class=rate_class.value)
            await asyncio.sleep(max(self._park_poll, min(wait, 6.0)))

"""Round-robin proxy pool: rotates across healthy proxies for each request.

Unlike StickyProxyPool there is no token→proxy pin; every acquire picks the
next healthy proxy in rotation.  Useful for anonymous/fire-and-forget calls.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from pylzt.lib.clock import RealClock
from pylzt.lib.metrics import NullMetrics
from pylzt.proxy_pool.base import BaseProxyPool, BaseProxySource, Proxy
from pylzt.proxy_pool.health import ProxyHealth

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pylzt.lib.clock import Clock
    from pylzt.lib.metrics import BaseMetrics
    from pylzt.types import ProxyId, ProxyOutcome, TokenId


class RoundRobinProxyPool(BaseProxyPool):
    """Stateless rotation across available proxies with per-proxy bulkhead."""

    def __init__(
        self,
        source: BaseProxySource,
        *,
        max_concurrency: int = 8,
        clock: Clock | None = None,
        metrics: BaseMetrics | None = None,
    ) -> None:
        self._clock = clock or RealClock()
        self._metrics = metrics or NullMetrics()

        self._proxies: list[Proxy] = list(source.load())
        self._health: dict[ProxyId, ProxyHealth] = {
            p.proxy_id: ProxyHealth(proxy_id=p.proxy_id) for p in self._proxies
        }
        self._semaphores: dict[ProxyId, asyncio.Semaphore] = {
            p.proxy_id: asyncio.Semaphore(max_concurrency) for p in self._proxies
        }
        self._cursor: int = 0
        self._lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def acquire(self, token_id: TokenId) -> AsyncIterator[Proxy | None]:
        if not self._proxies:
            yield None
            return

        proxy = await self._next_healthy()
        if proxy is None:
            yield None
            return

        async with self._semaphores[proxy.proxy_id]:
            yield proxy

    async def _next_healthy(self) -> Proxy | None:
        """Advance cursor and return the first available proxy; None if all cooling."""
        async with self._lock:
            n = len(self._proxies)
            for _ in range(n):
                proxy = self._proxies[self._cursor % n]
                self._cursor = (self._cursor + 1) % n
                if self._health[proxy.proxy_id].is_available(self._clock):
                    return proxy
        return None

    def report(self, proxy_id: ProxyId, outcome: ProxyOutcome) -> None:
        if proxy_id in self._health:
            self._health[proxy_id].report(outcome, self._clock)

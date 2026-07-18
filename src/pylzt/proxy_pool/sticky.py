"""Sticky proxy pool: each API token is pinned to one proxy for the session.

Prevents IP-switching mid-session which triggers rate-limit resets and account
bans on lzt.market.  Each proxy is guarded by a per-proxy asyncio.Semaphore
(bulkhead) and a circuit-breaker (ProxyHealth).
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


class StickyProxyPool(BaseProxyPool):
    """Token → proxy pin map with per-proxy circuit-breaker and bulkhead."""

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

        loaded = list(source.load())
        self._proxies: dict[ProxyId, Proxy] = {p.proxy_id: p for p in loaded}
        self._health: dict[ProxyId, ProxyHealth] = {
            p.proxy_id: ProxyHealth(proxy_id=p.proxy_id) for p in loaded
        }
        self._semaphores: dict[ProxyId, asyncio.Semaphore] = {
            p.proxy_id: asyncio.Semaphore(max_concurrency) for p in loaded
        }
        self._pins: dict[TokenId, ProxyId] = {}
        self._lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def acquire(self, token_id: TokenId) -> AsyncIterator[Proxy | None]:
        if not self._proxies:
            yield None
            return

        proxy_id = await self._ensure_pin(token_id)

        # Park until the circuit-breaker clears (OPEN → cooldown elapsed → HALF_OPEN)
        while not self._health[proxy_id].is_available(self._clock):
            wait = self._health[proxy_id].time_until_available(self._clock)
            await asyncio.sleep(max(0.05, min(wait, 1.0)))

        async with self._semaphores[proxy_id]:
            yield self._proxies[proxy_id]

    async def _ensure_pin(self, token_id: TokenId) -> ProxyId:
        """Return existing pin or assign the best available free proxy."""
        async with self._lock:
            if token_id in self._pins:
                return self._pins[token_id]

            pinned = set(self._pins.values())
            chosen: ProxyId | None = None

            # Prefer a free proxy that is also healthy right now
            for pid in self._proxies:
                if pid not in pinned and self._health[pid].is_available(self._clock):
                    chosen = pid
                    break

            # Fallback: any free proxy (will park in the loop above if cooling)
            if chosen is None:
                for pid in self._proxies:
                    if pid not in pinned:
                        chosen = pid
                        break

            if chosen is None:
                raise RuntimeError("proxy pool exhausted: all proxies are already pinned")

            self._pins[token_id] = chosen
            return chosen

    def report(self, proxy_id: ProxyId, outcome: ProxyOutcome) -> None:
        if proxy_id in self._health:
            self._health[proxy_id].report(outcome, self._clock)


class NullProxyPool(BaseProxyPool):
    """No-op pool used when proxy support is disabled; always yields None."""

    @contextlib.asynccontextmanager
    async def acquire(self, token_id: TokenId) -> AsyncIterator[Proxy | None]:
        yield None

    def report(self, proxy_id: ProxyId, outcome: ProxyOutcome) -> None:
        return None

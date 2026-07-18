"""`BaseCache` / `MemoryCache` — TTL expiry and client read-through injection."""

from __future__ import annotations

from pylzt.client import Client
from pylzt.lib.cache import BaseCache, MemoryCache, server_cache_ttl
from pylzt.lib.clock import FakeClock
from pylzt.models.category import FilterSchema
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import Category, TokenId


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


def test_server_cache_ttl_reads_origin_declared_window() -> None:
    # The Market search/list endpoints ship `cacheTTL` (seconds) alongside `wasCached`.
    assert server_cache_ttl({"cacheTTL": 900, "wasCached": True}) == 900.0
    assert server_cache_ttl({"cacheTTL": 0}) is None  # 0 = not cacheable, not "expire now"
    assert server_cache_ttl({}) is None  # endpoint omits it → caller uses its config default
    assert server_cache_ttl({"cacheTTL": True}) is None  # bool must not read as 1.0s


async def test_memory_cache_returns_until_ttl_then_expires() -> None:
    clock = FakeClock()
    cache: MemoryCache[int] = MemoryCache(clock=clock)
    await cache.set("k", 7, ttl=10.0)

    assert await cache.get("k") == 7
    clock.advance(9.9)
    assert await cache.get("k") == 7  # still inside the window
    clock.advance(0.2)
    assert await cache.get("k") is None  # expired and evicted
    assert await cache.get("missing") is None


class _CountingTransport(BaseTransport):
    """Counts calls so we can prove the cache spares the wire on a hit."""

    def __init__(self) -> None:
        super().__init__(token_pool=_pool())
        self.calls = 0

    async def _send_raw(self, req: Request) -> Response:
        self.calls += 1
        return Response(status=200, body={"schema": req.path})

    async def aclose(self) -> None:
        return None


async def test_client_category_params_is_cached_read_through() -> None:
    transport = _CountingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        first = await client.market.category_params(Category.STEAM)
        second = await client.market.category_params(Category.STEAM)
        other = await client.market.category_params(Category.DISCORD)

    assert first == second
    assert transport.calls == 2  # STEAM fetched once (2nd served from cache), DISCORD once
    assert other != first


async def test_injected_cache_backend_is_used() -> None:
    class _Recording(MemoryCache[FilterSchema]):
        def __init__(self) -> None:
            super().__init__()
            self.sets = 0

        async def set(self, key: str, value: FilterSchema, *, ttl: float) -> None:
            self.sets += 1
            await super().set(key, value, ttl=ttl)

    injected: _Recording = _Recording()
    transport = _CountingTransport()
    async with Client(tokens=["tok"], transport=transport, category_cache=injected) as client:
        await client.market.category_params(Category.STEAM)

    assert injected.sets == 1  # the injected backend received the write, not a module global


def test_cache_is_an_abc_seam() -> None:
    assert issubclass(MemoryCache, BaseCache)

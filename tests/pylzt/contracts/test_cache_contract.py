"""Shared contract for `BaseCache` — roundtrip, miss, overwrite (clock-independent).

TTL expiry is clock-driven and lives in the impl-specific test (`test_cache.py` exercises
`MemoryCache` with a `FakeClock`); this suite pins the semantics every backend — including
a future Redis impl for `autobuy` — must satisfy without a controllable clock.
"""

from __future__ import annotations

from pylzt.lib.cache import BaseCache, MemoryCache


class BaseCacheContract:
    def make_cache(self) -> BaseCache[str]:
        raise NotImplementedError

    async def test_roundtrip(self) -> None:
        cache = self.make_cache()
        await cache.set("k", "v", ttl=60.0)
        assert await cache.get("k") == "v"

    async def test_miss_returns_none(self) -> None:
        assert await self.make_cache().get("absent") is None

    async def test_overwrite_wins(self) -> None:
        cache = self.make_cache()
        await cache.set("k", "a", ttl=60.0)
        await cache.set("k", "b", ttl=60.0)
        assert await cache.get("k") == "b"


class TestMemoryCache(BaseCacheContract):
    def make_cache(self) -> BaseCache[str]:
        return MemoryCache()

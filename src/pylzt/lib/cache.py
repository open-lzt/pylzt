"""TTL cache seam — a keyed, expiring store behind an ABC (Law 16 / D-TTL).

The category-params endpoint is cached so a hot path doesn't re-fetch a filter
schema that only changes hourly. The cache is a pluggable primitive: ship an
in-memory default (`MemoryCache`, Law 11), let a consumer inject Redis/memcached
without the SDK importing either. `get` / `set` are async so a network-backed
backend is a drop-in for the in-process one — the caller never changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from pylzt.lib.clock import Clock, RealClock


def server_cache_ttl(body: Mapping[str, Any]) -> float | None:
    """The origin's own freshness window for a response, in seconds.

    The Market search/list endpoints ship a `cacheTTL` integer (alongside
    `wasCached` / `lastModified`) declaring how long the payload is good for. Prefer
    it over a static client guess so a cache entry expires when the server says it
    should. Returns `None` when the response omits it (caller falls back to config).
    """
    raw = body.get("cacheTTL")
    if isinstance(raw, bool):  # bool is an int subclass — a stray True must not become 1.0s
        return None
    if isinstance(raw, int | float) and raw > 0:
        return float(raw)
    return None


class BaseCache[T](ABC):
    """A keyed store with per-entry TTL. The impl decides where the bytes live."""

    @abstractmethod
    async def get(self, key: str) -> T | None:
        """Return the live value for `key`, or `None` if absent or expired."""

    @abstractmethod
    async def set(self, key: str, value: T, *, ttl: float) -> None:
        """Store `value` under `key`, expiring `ttl` seconds from now."""


class MemoryCache[T](BaseCache[T]):
    """In-process TTL cache (Law 11 default). Monotonic-clock expiry, no eviction cap."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or RealClock()
        self._entries: dict[str, tuple[float, T]] = {}

    async def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock.monotonic() >= expires_at:
            del self._entries[key]
            return None
        return value

    async def set(self, key: str, value: T, *, ttl: float) -> None:
        self._entries[key] = (self._clock.monotonic() + ttl, value)

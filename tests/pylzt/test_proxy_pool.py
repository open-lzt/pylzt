"""Tests for proxy_pool: health circuit-breaker, sources, sticky pool, round-robin."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pylzt.lib.clock import FakeClock

if TYPE_CHECKING:
    from pathlib import Path
from pylzt.proxy_pool.base import Proxy
from pylzt.proxy_pool.health import ProxyHealth
from pylzt.proxy_pool.round_robin import RoundRobinProxyPool
from pylzt.proxy_pool.source import EnvProxySource, FileProxySource, StaticProxySource
from pylzt.proxy_pool.sticky import NullProxyPool, StickyProxyPool
from pylzt.types import ProxyId, ProxyOutcome, ProxyScheme, TokenId


def make_proxy(
    proxy_id_str: str,
    scheme: ProxyScheme = ProxyScheme.HTTP,
) -> Proxy:
    """Build a Proxy where host == proxy_id_str for uniqueness across the pool."""
    pid = ProxyId(f"{scheme}://{proxy_id_str}:1080")
    return Proxy(proxy_id=pid, scheme=scheme, host=proxy_id_str, port=1080, auth=None)


def test_health_ok_keeps_closed() -> None:
    clock = FakeClock()
    h = ProxyHealth(proxy_id=ProxyId("p1"))
    h.report(ProxyOutcome.OK, clock)
    assert h.is_available(clock)


def test_health_conn_fail_threshold() -> None:
    clock = FakeClock()
    h = ProxyHealth(proxy_id=ProxyId("p1"))
    h.report(ProxyOutcome.CONN_FAIL, clock)
    h.report(ProxyOutcome.CONN_FAIL, clock)
    assert h.is_available(clock)  # 2 failures, threshold=3 → still open
    h.report(ProxyOutcome.CONN_FAIL, clock)
    assert not h.is_available(clock)  # tripped at threshold


def test_health_banned_trips_immediately() -> None:
    clock = FakeClock()
    h = ProxyHealth(proxy_id=ProxyId("p1"))
    h.report(ProxyOutcome.BANNED, clock)
    assert not h.is_available(clock)


def test_health_cooldown_elapses() -> None:
    clock = FakeClock()
    h = ProxyHealth(proxy_id=ProxyId("p1"), base_cooldown=30.0)
    h.report(ProxyOutcome.BANNED, clock)
    clock.advance(31.0)
    assert h.is_available(clock)  # transitions to HALF_OPEN


def test_health_recovery_closes() -> None:
    clock = FakeClock()
    h = ProxyHealth(proxy_id=ProxyId("p1"), base_cooldown=30.0)
    h.report(ProxyOutcome.BANNED, clock)
    clock.advance(31.0)
    assert h.is_available(clock)  # HALF_OPEN
    h.report(ProxyOutcome.OK, clock)
    assert h.is_available(clock)  # CLOSED


def test_health_re_trip_increases_cooldown() -> None:
    clock = FakeClock()
    h = ProxyHealth(proxy_id=ProxyId("p1"), base_cooldown=10.0)
    h.report(ProxyOutcome.BANNED, clock)  # trip 1: cooldown=10
    clock.advance(11.0)
    assert h.is_available(clock)  # HALF_OPEN
    h.report(ProxyOutcome.BANNED, clock)  # trip 2: cooldown=20
    assert h.time_until_available(clock) > 15.0  # longer than first


def test_health_max_cooldown_cap() -> None:
    clock = FakeClock()
    h = ProxyHealth(proxy_id=ProxyId("p1"), base_cooldown=100.0, max_cooldown=500.0)
    for _ in range(10):
        h.report(ProxyOutcome.BANNED, clock)
        clock.advance(600.0)
    h.report(ProxyOutcome.BANNED, clock)
    assert h.time_until_available(clock) <= 500.0


def test_static_source() -> None:
    proxies = [make_proxy("p1"), make_proxy("p2")]
    source = StaticProxySource(proxies)
    assert list(source.load()) == proxies


def test_file_source_parses_proxies(tmp_path: Path) -> None:
    f = tmp_path / "proxies.txt"
    f.write_text(
        "socks5://user:pass@127.0.0.1:1080\n# comment\n\nhttp://10.0.0.1:3128\n",
        encoding="utf-8",
    )
    source = FileProxySource(f)
    loaded = list(source.load())
    assert len(loaded) == 2
    assert loaded[0].scheme == ProxyScheme.SOCKS5
    assert loaded[0].auth is not None
    assert loaded[1].scheme == ProxyScheme.HTTP
    assert loaded[1].auth is None


def test_env_source(monkeypatch: object) -> None:
    import pytest

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEST_PROXIES", "http://a:b@1.2.3.4:80,https://5.6.7.8:443")
        source = EnvProxySource("TEST_PROXIES")
        loaded = list(source.load())
    assert len(loaded) == 2


async def test_sticky_two_tokens_different_proxies() -> None:
    source = StaticProxySource([make_proxy("p1"), make_proxy("p2")])
    pool = StickyProxyPool(source)
    async with pool.acquire(TokenId("tokA")) as pA:
        async with pool.acquire(TokenId("tokB")) as pB:
            assert pA is not None and pB is not None
            assert pA.proxy_id != pB.proxy_id


async def test_sticky_pin_is_stable() -> None:
    source = StaticProxySource([make_proxy("p1"), make_proxy("p2")])
    pool = StickyProxyPool(source)
    async with pool.acquire(TokenId("tokA")) as p1:
        pid1 = p1.proxy_id if p1 else None
    async with pool.acquire(TokenId("tokA")) as p2:
        pid2 = p2.proxy_id if p2 else None
    assert pid1 == pid2


async def test_sticky_parks_until_recovery() -> None:
    clock = FakeClock()
    source = StaticProxySource([make_proxy("p1")])
    pool = StickyProxyPool(source, clock=clock)

    # The pool loaded exactly one proxy; grab its id directly
    proxy_id = next(iter(pool._health))

    # Replace its health entry with a tiny-cooldown variant
    pool._health[proxy_id] = ProxyHealth(proxy_id=proxy_id, base_cooldown=0.001)

    # Trip the proxy
    pool.report(proxy_id, ProxyOutcome.BANNED)
    assert not pool._health[proxy_id].is_available(clock)

    result: list[Proxy] = []

    async def do_acquire() -> None:
        async with pool.acquire(TokenId("tokA")) as p:
            if p is not None:
                result.append(p)

    task = asyncio.create_task(do_acquire())
    await asyncio.sleep(0)  # yield: task starts, enters park loop
    assert not task.done()  # still sleeping in the park loop

    # Advance fake clock past the 0.001s cooldown
    clock.advance(1.0)
    await asyncio.sleep(0.15)  # real time: let the 0.05s poll cycle fire

    assert task.done()
    assert len(result) == 1
    assert result[0].proxy_id == proxy_id


async def test_sticky_never_shares_proxy() -> None:
    clock = FakeClock()
    source = StaticProxySource([make_proxy("p1"), make_proxy("p2")])
    pool = StickyProxyPool(source, clock=clock)

    async with pool.acquire(TokenId("tokA")) as pA:
        assert pA is not None
        pid_a = pA.proxy_id

    # Trip the proxy that tokA is pinned to
    pool.report(pid_a, ProxyOutcome.BANNED)

    # tokB must get the OTHER proxy
    async with pool.acquire(TokenId("tokB")) as pB:
        assert pB is not None
        assert pB.proxy_id != pid_a

    # tokA is still pinned to its original (cooling) proxy
    assert pool._pins[TokenId("tokA")] == pid_a


async def test_bulkhead_caps_concurrency() -> None:
    source = StaticProxySource([make_proxy("p1")])
    pool = StickyProxyPool(source, max_concurrency=2)

    active = 0
    max_active = 0

    async def hold() -> None:
        nonlocal active, max_active
        async with pool.acquire(TokenId("tok")) as _:
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            active -= 1

    await asyncio.gather(hold(), hold(), hold())
    assert max_active <= 2


async def test_null_pool_yields_none() -> None:
    pool = NullProxyPool()
    async with pool.acquire(TokenId("tok")) as p:
        assert p is None


def test_null_pool_report_noop() -> None:
    pool = NullProxyPool()
    pool.report(ProxyId("any"), ProxyOutcome.BANNED)  # must not raise


async def test_round_robin_rotates() -> None:
    source = StaticProxySource([make_proxy("p1"), make_proxy("p2")])
    pool = RoundRobinProxyPool(source)
    seen: list[ProxyId] = []
    for i in range(4):
        async with pool.acquire(TokenId(f"tok{i}")) as p:
            if p:
                seen.append(p.proxy_id)
    assert len(set(seen)) == 2


async def test_round_robin_skips_cooling() -> None:
    clock = FakeClock()
    source = StaticProxySource([make_proxy("p1"), make_proxy("p2")])
    pool = RoundRobinProxyPool(source, clock=clock)

    async with pool.acquire(TokenId("tok0")) as p0:
        assert p0 is not None
        first_id = p0.proxy_id

    # Trip the first proxy that was returned
    pool.report(first_id, ProxyOutcome.BANNED)

    # Next acquire must skip the cooling proxy
    async with pool.acquire(TokenId("tok1")) as p1:
        assert p1 is not None
        assert p1.proxy_id != first_id

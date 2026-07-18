"""Token-bucket + pool tests — the paranoid-coverage component (a bug = bans)."""

from __future__ import annotations

import asyncio

import pytest

from pylzt.config import ClientConfig
from pylzt.lib.clock import FakeClock
from pylzt.token_pool._static import NoUsableCredential, _StaticBearerPool
from pylzt.token_pool.base import Token
from pylzt.token_pool.bucket import RateBucketSet, TokenBucket
from pylzt.token_pool.rate_limit import RateLimitSnapshot
from pylzt.token_pool.round_robin import NoUsableToken, RoundRobinTokenPool
from pylzt.types import RateClass, TokenId


def test_bucket_drains_to_exactly_capacity() -> None:
    clock = FakeClock()
    bucket = TokenBucket.per_minute(20, clock)
    assert all(bucket.try_consume(clock) for _ in range(20))
    assert bucket.try_consume(clock) is False  # 21st over budget — never granted


def test_bucket_refills_continuously() -> None:
    clock = FakeClock()
    bucket = TokenBucket.per_minute(60, clock)  # 1 token/sec
    for _ in range(60):
        bucket.try_consume(clock)
    assert bucket.try_consume(clock) is False
    clock.advance(1.0)
    assert bucket.try_consume(clock) is True  # one refilled
    assert bucket.try_consume(clock) is False


def test_bucket_time_until() -> None:
    clock = FakeClock()
    bucket = TokenBucket.per_minute(60, clock)
    for _ in range(60):
        bucket.try_consume(clock)
    assert bucket.time_until(clock) == pytest.approx(1.0, abs=0.01)
    clock.advance(0.5)
    assert bucket.time_until(clock) == pytest.approx(0.5, abs=0.01)


def test_bucket_classes_independent() -> None:
    clock = FakeClock()
    buckets = RateBucketSet.standard(clock, general=20, search=10)
    for _ in range(10):
        assert buckets.try_consume(RateClass.SEARCH, clock)
    assert buckets.try_consume(RateClass.SEARCH, clock) is False  # search exhausted
    assert buckets.try_consume(RateClass.GENERAL, clock) is True  # general untouched


def test_default_limits_match_official_published_ceilings() -> None:
    # lzt-market.readme.io / lolzteam.readme.io "Rate limit" sections (2026-07-04).
    # These bound money/order request paths — a silent bump risks account bans.
    cfg = ClientConfig()
    assert (cfg.general_per_min, cfg.search_per_min, cfg.forum_per_min) == (120, 20, 300)

    clock = FakeClock()
    buckets = RateBucketSet.standard(clock)
    assert all(buckets.try_consume(RateClass.SEARCH, clock) for _ in range(20))
    assert buckets.try_consume(RateClass.SEARCH, clock) is False  # 21st search over ceiling


def test_forum_bucket_independent_of_general_and_search() -> None:
    clock = FakeClock()
    buckets = RateBucketSet.standard(clock, general=20, search=10, forum=5)
    for _ in range(5):
        assert buckets.try_consume(RateClass.FORUM, clock)
    assert buckets.try_consume(RateClass.FORUM, clock) is False  # forum exhausted
    assert buckets.try_consume(RateClass.GENERAL, clock) is True  # general untouched
    assert buckets.try_consume(RateClass.SEARCH, clock) is True  # search untouched


async def test_pool_leases_forum_rate_class_independently() -> None:
    clock = FakeClock()
    pool = RoundRobinTokenPool(_tokens(1), clock=clock, forum_per_min=5)
    for _ in range(5):
        async with pool.lease(RateClass.FORUM) as lease:
            assert str(lease.token.token_id) == "t0"
    # forum budget exhausted, but general is a distinct bucket on the same token
    async with pool.lease(RateClass.GENERAL) as lease:
        assert str(lease.token.token_id) == "t0"


def _tokens(n: int) -> list[Token]:
    return [Token(token_id=TokenId(f"t{i}"), credential=f"cred{i}") for i in range(n)]


async def test_pool_rotates_across_tokens() -> None:
    clock = FakeClock()
    pool = RoundRobinTokenPool(_tokens(2), clock=clock)
    seen: set[str] = set()
    for _ in range(2):
        async with pool.lease(RateClass.GENERAL) as lease:
            seen.add(str(lease.token.token_id))
    assert seen == {"t0", "t1"}  # rotated, not stuck on one


async def test_pool_quarantine_removes_token() -> None:
    clock = FakeClock()
    pool = RoundRobinTokenPool(_tokens(2), clock=clock)
    pool.quarantine(TokenId("t0"))
    for _ in range(5):
        async with pool.lease(RateClass.GENERAL) as lease:
            assert str(lease.token.token_id) == "t1"  # quarantined token never leased


async def test_pool_all_quarantined_raises() -> None:
    clock = FakeClock()
    pool = RoundRobinTokenPool(_tokens(1), clock=clock)
    pool.quarantine(TokenId("t0"))
    with pytest.raises(NoUsableToken):
        async with pool.lease(RateClass.GENERAL):
            pass


def test_empty_pool_rejected() -> None:
    with pytest.raises(NoUsableToken):
        RoundRobinTokenPool([])


def test_bucket_reconcile_clamps_down_to_server_remaining() -> None:
    clock = FakeClock()
    bucket = TokenBucket.per_minute(20, clock)  # 20 tokens available locally
    bucket.reconcile(remaining=5, clock=clock)
    assert bucket.available(clock) == 5


def test_bucket_reconcile_never_raises_above_local_estimate() -> None:
    clock = FakeClock()
    bucket = TokenBucket.per_minute(20, clock)
    bucket.try_consume(clock)  # 19 left locally
    bucket.reconcile(remaining=100, clock=clock)  # server claims more — ignored
    assert bucket.available(clock) == 19


def test_rate_bucket_set_reconcile_unknown_rate_class_is_noop() -> None:
    clock = FakeClock()
    buckets = RateBucketSet.standard(clock)
    snapshot = RateLimitSnapshot(limit=60, remaining=1, reset=0)
    buckets.reconcile(RateClass.ANTIPUBLIC, snapshot, clock)  # no KeyError, silent no-op


async def test_pool_report_rate_limit_clamps_matching_token_bucket() -> None:
    clock = FakeClock()
    pool = RoundRobinTokenPool(_tokens(2), clock=clock)
    snapshot = RateLimitSnapshot(limit=120, remaining=3, reset=0)
    pool.report_rate_limit(TokenId("t0"), RateClass.GENERAL, snapshot)
    assert pool._buckets[TokenId("t0")]._select(RateClass.GENERAL).available(clock) == 3
    # t1 untouched
    assert pool._buckets[TokenId("t1")]._select(RateClass.GENERAL).available(clock) == 120


async def test_pool_report_rate_limit_unknown_token_id_is_noop() -> None:
    clock = FakeClock()
    pool = RoundRobinTokenPool(_tokens(1), clock=clock)
    snapshot = RateLimitSnapshot(limit=120, remaining=3, reset=0)
    pool.report_rate_limit(TokenId("quarantined-mid-flight"), RateClass.GENERAL, snapshot)
    assert pool._buckets[TokenId("t0")]._select(RateClass.GENERAL).available(clock) == 120


class TestRateLimitSnapshotFromBody:
    def test_valid_body_parses(self) -> None:
        body = {
            "system_info": {
                "rate_limit": {"limit": 120, "remaining": 90, "reset": 1234, "bucket": "b1"}
            }
        }
        snapshot = RateLimitSnapshot.from_body(body)
        assert snapshot == RateLimitSnapshot(limit=120, remaining=90, reset=1234, bucket="b1")

    def test_missing_bucket_field_defaults_to_none(self) -> None:
        body = {"system_info": {"rate_limit": {"limit": 60, "remaining": 1, "reset": 0}}}
        snapshot = RateLimitSnapshot.from_body(body)
        assert snapshot is not None
        assert snapshot.bucket is None

    def test_missing_system_info_returns_none(self) -> None:
        assert RateLimitSnapshot.from_body({"status": "ok"}) is None

    def test_missing_rate_limit_returns_none(self) -> None:
        assert RateLimitSnapshot.from_body({"system_info": {}}) is None

    def test_malformed_rate_limit_type_returns_none(self) -> None:
        assert RateLimitSnapshot.from_body({"system_info": {"rate_limit": "oops"}}) is None

    def test_malformed_field_type_returns_none_not_raise(self) -> None:
        body = {"system_info": {"rate_limit": {"limit": "not-an-int", "remaining": 1, "reset": 0}}}
        assert RateLimitSnapshot.from_body(body) is None


async def test_static_bearer_pool_leases_the_fixed_credential() -> None:
    clock = FakeClock()
    pool = _StaticBearerPool(key="license-key", per_min=60, clock=clock)
    async with pool.lease(RateClass.ANTIPUBLIC) as lease:
        assert lease.token.credential == "license-key"
        assert lease.proxy is None


async def test_static_bearer_pool_parks_until_refill() -> None:
    # Real (unfaked) clock: the park loop sleeps real wall time, same as
    # RoundRobinTokenPool — a FakeClock jump doesn't unblock an in-flight asyncio.sleep.
    pool = _StaticBearerPool(key="license-key", per_min=120)  # 2/sec
    async with pool.lease(RateClass.ANTIPUBLIC):
        pass
    async with pool.lease(RateClass.ANTIPUBLIC):
        pass
    # Bucket is near-empty; the next lease must park briefly, not raise or hang.
    async with asyncio.timeout(2.0), pool.lease(RateClass.ANTIPUBLIC) as lease:
        assert lease.token.credential == "license-key"


async def test_static_bearer_pool_quarantine_rejects_further_leases() -> None:
    pool = _StaticBearerPool(key="license-key", clock=FakeClock())
    pool.quarantine(TokenId("antipublic"))
    with pytest.raises(NoUsableCredential):
        async with pool.lease(RateClass.ANTIPUBLIC):
            pass

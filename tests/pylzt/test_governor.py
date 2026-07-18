"""`AimdConcurrencyGovernor` — AIMD tuning off `RateLimitSnapshot.remaining/limit`."""

from __future__ import annotations

from pylzt.token_pool.governor import AimdConcurrencyGovernor, NullConcurrencyGovernor
from pylzt.token_pool.rate_limit import RateLimitSnapshot
from pylzt.types import RateClass


def test_danger_ratio_breach_halves_limit() -> None:
    gov = AimdConcurrencyGovernor(initial_limit=8, min_limit=1, danger_ratio=0.1)
    snapshot = RateLimitSnapshot(limit=100, remaining=5, reset=0)  # ratio 0.05 < 0.1

    gov.observe(RateClass.GENERAL, snapshot)

    assert gov.gate(RateClass.GENERAL).limit == 4


def test_danger_ratio_breach_clamps_to_min_limit() -> None:
    gov = AimdConcurrencyGovernor(initial_limit=1, min_limit=1, danger_ratio=0.1)
    snapshot = RateLimitSnapshot(limit=100, remaining=1, reset=0)

    gov.observe(RateClass.GENERAL, snapshot)

    assert gov.gate(RateClass.GENERAL).limit == 1  # 1 // 2 == 0, clamped up to min_limit


def test_safe_ratio_breach_increments_by_step() -> None:
    gov = AimdConcurrencyGovernor(initial_limit=8, max_limit=32, increase_step=2, safe_ratio=0.5)
    snapshot = RateLimitSnapshot(limit=100, remaining=90, reset=0)  # ratio 0.9 > 0.5

    gov.observe(RateClass.GENERAL, snapshot)

    assert gov.gate(RateClass.GENERAL).limit == 10


def test_safe_ratio_breach_clamps_to_max_limit() -> None:
    gov = AimdConcurrencyGovernor(initial_limit=31, max_limit=32, increase_step=5, safe_ratio=0.5)
    snapshot = RateLimitSnapshot(limit=100, remaining=90, reset=0)

    gov.observe(RateClass.GENERAL, snapshot)

    assert gov.gate(RateClass.GENERAL).limit == 32


def test_mid_range_ratio_is_a_noop() -> None:
    gov = AimdConcurrencyGovernor(initial_limit=8, danger_ratio=0.1, safe_ratio=0.5)
    snapshot = RateLimitSnapshot(limit=100, remaining=30, reset=0)  # ratio 0.3, in between

    gov.observe(RateClass.GENERAL, snapshot)

    assert gov.gate(RateClass.GENERAL).limit == 8


def test_rate_classes_tune_independently() -> None:
    gov = AimdConcurrencyGovernor(initial_limit=8, danger_ratio=0.1)
    gov.observe(RateClass.GENERAL, RateLimitSnapshot(limit=100, remaining=1, reset=0))

    assert gov.gate(RateClass.GENERAL).limit == 4
    assert gov.gate(RateClass.SEARCH).limit == 8  # untouched


def test_null_governor_never_resizes_regardless_of_snapshot() -> None:
    gov = NullConcurrencyGovernor(fixed_limit=8)
    gov.observe(RateClass.GENERAL, RateLimitSnapshot(limit=100, remaining=1, reset=0))
    gov.observe(RateClass.GENERAL, RateLimitSnapshot(limit=100, remaining=99, reset=0))

    assert gov.gate(RateClass.GENERAL).limit == 8

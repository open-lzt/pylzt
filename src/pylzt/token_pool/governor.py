"""AIMD concurrency governor — retunes live parallelism off the server's
`RateLimitSnapshot` signal instead of a static config knob.

Deliberately separate from the per-proxy `asyncio.Semaphore` bulkhead in
`proxy_pool/`: that bounds concurrent use of one IP (anti-ban), an invariant
independent of a token's API rate budget. This governor gets its own gate
per `RateClass`, composed alongside the proxy bulkhead in
`BaseTransport.send()`, not a repurposing of it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pylzt.lib.concurrency import AdaptiveGate
from pylzt.lib.metrics import BaseMetrics, NullMetrics
from pylzt.token_pool.rate_limit import RateLimitSnapshot
from pylzt.types import RateClass


class BaseConcurrencyGovernor(ABC):
    @abstractmethod
    def gate(self, rate_class: RateClass) -> AdaptiveGate:
        """The gate to acquire before a request in `rate_class` is sent."""

    @abstractmethod
    def observe(self, rate_class: RateClass, snapshot: RateLimitSnapshot) -> None:
        """Retune the matching gate from a server-reported budget snapshot."""


class NullConcurrencyGovernor(BaseConcurrencyGovernor):
    """Default: fixed-limit gates, `observe()` is a no-op. Mirrors `NullMetrics`.

    `fixed_limit` defaults effectively unlimited, not a "sane default" cap —
    `BaseTransport.send()` always wraps a request in `gate(...).acquire()`
    regardless of `enable_adaptive_concurrency`, so a small default here would
    silently throttle every client that never opted into AIMD tuning. The gate
    still exists (so the admission-control seam is uniform), it just never binds."""

    def __init__(self, fixed_limit: int = 1 << 20) -> None:
        self._fixed_limit = fixed_limit
        self._gates: dict[RateClass, AdaptiveGate] = {}

    def gate(self, rate_class: RateClass) -> AdaptiveGate:
        if rate_class not in self._gates:
            self._gates[rate_class] = AdaptiveGate(self._fixed_limit)
        return self._gates[rate_class]

    def observe(self, rate_class: RateClass, snapshot: RateLimitSnapshot) -> None:
        return None


class AimdConcurrencyGovernor(BaseConcurrencyGovernor):
    """Additive-increase / multiplicative-decrease off `remaining/limit`.

    Below `danger_ratio` → halve (clamped to `min_limit`); above `safe_ratio`
    → +`increase_step` (clamped to `max_limit`); in between → no-op. Standard
    asymmetric AIMD shape: cut hard on danger, grow slowly when safe.
    """

    def __init__(
        self,
        *,
        initial_limit: int = 8,
        min_limit: int = 1,
        max_limit: int = 32,
        increase_step: int = 1,
        danger_ratio: float = 0.1,
        safe_ratio: float = 0.5,
        metrics: BaseMetrics | None = None,
    ) -> None:
        self._initial_limit = initial_limit
        self._min_limit = min_limit
        self._max_limit = max_limit
        self._increase_step = increase_step
        self._danger_ratio = danger_ratio
        self._safe_ratio = safe_ratio
        self._metrics = metrics or NullMetrics()
        self._gates: dict[RateClass, AdaptiveGate] = {}

    def gate(self, rate_class: RateClass) -> AdaptiveGate:
        if rate_class not in self._gates:
            self._gates[rate_class] = AdaptiveGate(self._initial_limit)
        return self._gates[rate_class]

    def observe(self, rate_class: RateClass, snapshot: RateLimitSnapshot) -> None:
        if snapshot.limit <= 0:
            return  # malformed/zero-limit snapshot — nothing sane to divide by
        gate = self.gate(rate_class)
        ratio = snapshot.remaining / snapshot.limit
        if ratio < self._danger_ratio:
            new_limit = max(self._min_limit, gate.limit // 2)
        elif ratio > self._safe_ratio:
            new_limit = min(self._max_limit, gate.limit + self._increase_step)
        else:
            return
        if new_limit != gate.limit:
            gate.resize(new_limit)
            self._metrics.gauge(
                "adaptive_concurrency_limit", new_limit, rate_class=rate_class.value
            )

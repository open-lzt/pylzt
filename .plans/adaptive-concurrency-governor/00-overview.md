# adaptive-concurrency-governor — overview

**Tier:** module-lite · **Mode:** layered, solo, one pass
**🔵 BLOCKED — hard sequencing dependency, not just convenience.**
Cannot be built before `.plans/rate-limit-sync/` ships and merges:
`RateLimitSnapshot` and `BaseTokenPool.report_rate_limit` do not exist in
source yet (`verified-by-code`: confirmed absent from
`src/pylzt/token_pool/` at audit time — only `_static.py, base.py,
bucket.py, round_robin.py, selector.py` exist there today). **Do not start
`04-tasks.yaml` for this plan until `rate-limit-sync`'s `RELEASE-READY` task
is done and merged to `main`.**

## Goal
AIMD-style (additive-increase / multiplicative-decrease) auto-tuning of
request concurrency, driven by the `RateLimitSnapshot.remaining`/`limit`
ratio (from `rate-limit-sync`), replacing a static fixed concurrency limit.

## Scope
- **Not the existing proxy-pool semaphores.** Confirmed 🟡 correction: the
  per-proxy `asyncio.Semaphore` bulkheads in `RoundRobinProxyPool`/
  `StickyProxyPool` (`verified-by-code:src/pylzt/proxy_pool/round_robin.py:33,44-46`,
  `src/pylzt/proxy_pool/sticky.py:34,46-48`, default `max_concurrency=8`)
  bound concurrent use of one **IP** (anti-ban bulkhead) — an independent
  invariant from a token's API rate budget. Resizing them off the rate-limit
  signal would conflate two unrelated concerns (a proxy could be starved/
  over-granted for reasons that have nothing to do with a given token's
  budget; `RoundRobinProxyPool` has no token affinity at all). The governor
  gets its **own** gate, composed alongside the existing bulkhead, not a
  repurposing of it.
- **No resizable-bounded-resource primitive exists anywhere in the repo**
  (confirmed, grepped for `Semaphore`/`max_concurrency`). `asyncio.Semaphore`
  genuinely has no resize API. New primitive: `AdaptiveGate` in
  `lib/concurrency.py` — hand-rolled counter + FIFO waiter-future queue
  (structurally identical to `asyncio.Semaphore`'s own internals, except
  `_limit` is mutable and `resize()` is a plain **synchronous** method, safe
  to call from a non-async callback). Growing wakes queued waiters
  immediately; shrinking is lazy — in-flight holders over the new limit
  finish naturally, no forced eviction/cancellation. Rejected alternative:
  semaphore + fire-and-forget shrink task (risks an untracked
  `asyncio.ensure_future()` being GC'd mid-await, silently failing the
  shrink). `AdaptiveGate` is a genuinely reusable cross-cutting primitive
  (this project's rules explicitly name "throttle" as extract-on-sight) —
  belongs in `lib/` alongside `retry.py`/`metrics.py`/`clock.py` siblings.
- `BaseConcurrencyGovernor` ABC + `NullConcurrencyGovernor` (default,
  fixed-limit gates, `observe()` no-op — mirrors `NullMetrics` convention)
  + `AimdConcurrencyGovernor` (the real AIMD logic).
- Hook point: `RateLimitedTransport` (`src/pylzt/transport/rate_limited.py`),
  new optional constructor param `concurrency_governor: BaseConcurrencyGovernor
  | None = None` (default `NullConcurrencyGovernor()`), same DI-with-default
  convention as `retry`/`metrics`/`clock`. In `send()`, wrap the retry loop's
  per-attempt body in `async with self._concurrency_governor.gate(req.rate_class).acquire():`
  as the **outermost** layer (admission control before token lease) — new
  layer, composed with (not replacing) the existing proxy bulkhead. On the
  success branch, reuse the `RateLimitSnapshot` already parsed for
  `report_rate_limit` (rate-limit-sync's frozen call site,
  `rate_limited.py:70-73` per that plan's `00-overview.md`) — one parse, two
  consumers: token pool tightens its bucket, governor retunes concurrency
  via `governor.observe(req.rate_class, snapshot)`.
- `ClientConfig.enable_adaptive_concurrency: bool = False` — **default
  False**, unlike rate-limit-sync's `True` default. Rationale: clamp-only
  reconciliation in rate-limit-sync is inherently safe (only tightens); AIMD
  *actively changes* live throughput and can misfire (too aggressive or too
  lenient) — that's a behavior change, not a safety tightening, so it ships
  opt-in.

## Non-goals
- No resizing of proxy-pool semaphores (see Scope — wrong invariant).
- No cross-token/cross-rate-class shared gate — one `AdaptiveGate` per
  `RateClass` (mirrors `RateBucketSet`'s per-class bucket split).
- No persistence of the tuned limit across process restarts — starts fresh
  at `initial_limit` every boot (out of scope; a follow-up if warm-start
  proves valuable).

## Files touched
- `src/pylzt/lib/concurrency.py` — **new**, `AdaptiveGate`.
- `src/pylzt/token_pool/governor.py` (or `lib/concurrency.py` if small
  enough to stay in one file — decide at implementation time, default to
  separate file since `BaseConcurrencyGovernor` is a distinct ABC concern
  from the raw `AdaptiveGate` primitive) — `BaseConcurrencyGovernor`,
  `NullConcurrencyGovernor`, `AimdConcurrencyGovernor`.
- `src/pylzt/transport/rate_limited.py` — constructor param + `send()`
  wiring (gate acquire wraps retry-loop body; `observe()` call at the
  existing rate-limit-sync success-branch call site).
- `src/pylzt/config.py` — `enable_adaptive_concurrency: bool = False`.
- `tests/pylzt/test_concurrency.py` — **new**, `AdaptiveGate` grow/shrink/
  waiter-wakeup unit tests.
- `tests/pylzt/test_governor.py` — **new**, `AimdConcurrencyGovernor`
  AIMD math (danger-ratio halving, safe-ratio increment, clamping to
  min/max_limit).
- `tests/pylzt/test_rate_limited_transport.py` — governor wiring
  (gate acquired before lease; `observe()` called on success; toggle off →
  `NullConcurrencyGovernor` used, no resizing).

## Contracts/Types (frozen)

```python
# src/pylzt/lib/concurrency.py — new file
class AdaptiveGate:
    """Resizable concurrency gate. Structurally an asyncio.Semaphore with a
    mutable limit -- resize() is synchronous (safe from a non-async
    callback) and never forcibly evicts an in-flight holder; shrinks take
    effect as holders release."""

    def __init__(self, limit: int) -> None: ...  # raises ValueError if limit < 1

    @property
    def limit(self) -> int: ...

    def resize(self, new_limit: int) -> None: ...  # raises ValueError if < 1

    @contextlib.asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]: ...

# src/pylzt/token_pool/governor.py — new file
class BaseConcurrencyGovernor(ABC):
    @abstractmethod
    def gate(self, rate_class: RateClass) -> AdaptiveGate: ...
    @abstractmethod
    def observe(self, rate_class: RateClass, snapshot: RateLimitSnapshot) -> None: ...

class NullConcurrencyGovernor(BaseConcurrencyGovernor):
    def __init__(self, fixed_limit: int = 8) -> None: ...
    def gate(self, rate_class: RateClass) -> AdaptiveGate: ...  # lazy, never resized
    def observe(self, rate_class: RateClass, snapshot: RateLimitSnapshot) -> None:
        return None

class AimdConcurrencyGovernor(BaseConcurrencyGovernor):
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
    ) -> None: ...
    def gate(self, rate_class: RateClass) -> AdaptiveGate: ...
    def observe(self, rate_class: RateClass, snapshot: RateLimitSnapshot) -> None:
        """ratio = snapshot.remaining / snapshot.limit.
        ratio < danger_ratio -> gate.resize(max(min_limit, gate.limit // 2))
        ratio > safe_ratio   -> gate.resize(min(max_limit, gate.limit + increase_step))
        else -> no-op.
        Emits metrics.gauge('adaptive_concurrency_limit', new_limit, rate_class=rate_class.value)."""

# src/pylzt/transport/rate_limited.py — RateLimitedTransport, add:
def __init__(
    self,
    ...,  # existing params unchanged
    concurrency_governor: BaseConcurrencyGovernor | None = None,
) -> None:
    self._concurrency_governor = concurrency_governor or NullConcurrencyGovernor()

# send(): wrap retry-loop body in
#   async with self._concurrency_governor.gate(req.rate_class).acquire():
# success branch (after RateLimitSnapshot parsed for report_rate_limit):
#   self._concurrency_governor.observe(req.rate_class, snapshot)

# src/pylzt/config.py — ClientConfig, add field:
enable_adaptive_concurrency: bool = False
```

## Worktree
`../aiolzt-adaptive-concurrency-governor` on branch `feat/adaptive-concurrency-governor`, based on `main` — **created only after `rate-limit-sync` has merged** (branch base must include that merge).

## Risks / edge cases
- **Sequencing risk (the main one)**: if this plan is started before
  `rate-limit-sync` merges, every `RateLimitSnapshot`/`report_rate_limit`
  reference in the contracts above is building against a moving target.
  Mitigation: the BLOCKED banner at the top of this file; `04-tasks.yaml`'s
  T1 acceptance explicitly re-checks that the dependency landed before any
  code is written.
- **AIMD oscillation**: aggressive `danger_ratio`/`safe_ratio` defaults
  could thrash the limit up/down under bursty traffic. Defaults chosen
  conservatively (halve on danger, +1 on safe — asymmetric AIMD is the
  standard congestion-control shape); tuning is opt-in via constructor
  params, not hardcoded. `unverified` — no load-test data backs these
  specific numbers yet; flagged as a tuning risk, not a correctness one.
- **Gate leak on cancellation**: `AdaptiveGate.acquire()`'s `finally` block
  must decrement `_in_flight` and wake waiters even if the caller's task is
  cancelled mid-hold — cheap guard, included in the contract (`finally:`
  in the sketch above), not deferred.

## Success criteria (verifiable)
1. `AdaptiveGate.resize()` growing wakes queued waiters immediately;
   shrinking does not forcibly evict in-flight holders.
2. `AimdConcurrencyGovernor.observe()` halves the gate limit (clamped to
   `min_limit`) when `remaining/limit < danger_ratio`, increments by
   `increase_step` (clamped to `max_limit`) when `> safe_ratio`, no-ops
   otherwise.
3. `RateLimitedTransport.send()` acquires the governor's gate before
   leasing a token; toggle off → `NullConcurrencyGovernor` used, gate never
   resized regardless of response content.
4. Existing `RateLimitedTransport`/proxy-pool bulkhead tests stay green —
   no behavior change to the non-governor path.
5. `RELEASE-READY` pseudo-task passes.

## Decisions log
- **New `AdaptiveGate`, not resized proxy semaphores** —
  `verified-by-code:src/pylzt/proxy_pool/round_robin.py:33,44-46`
  (IP-bulkhead vs token-rate-budget are independent invariants).
- **Hand-rolled counter+waiter-queue, not semaphore+shrink-task** —
  `unverified` design call, reasoning: avoids untracked-task GC leak failure
  mode this project's defensive-programming rules flag.
- **`AdaptiveGate` lives in `lib/`** — `verified-by-code:.claude/rules/patterns.md`
  ("throttle" explicitly named extract-on-sight cross-cutting primitive).
- **Opt-in default (`False`)**, unlike rate-limit-sync's opt-out (`True`) —
  `unverified` product judgment call (AIMD changes behavior, clamp-only
  only tightens).

## Code-verification (W3.5, single Sonnet audit — module-lite)
Full Sonnet audit ran against real source. Confirmed all Haiku claims about
proxy-pool semaphores, `ClientConfig`, `MiddlewareManager`, `BaseMetrics`,
token-pool lease flow, and the rate-limit-sync plan's not-yet-built status.
Corrected framing: proxy semaphores are the wrong resize target (folded into
Scope above). Resolved the dynamic-semaphore feasibility question with the
`AdaptiveGate` design (no existing primitive to reuse, confirmed via repo-
wide grep). **Confirmed 🔴 blocker is sequencing, not feasibility** — this
plan's contracts are sound but cannot be implemented until `rate-limit-sync`
ships the types they depend on. No other 🔴 blockers.

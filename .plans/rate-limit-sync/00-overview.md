# rate-limit-sync — overview

**Tier:** module-lite · **Mode:** layered, solo, one pass · **🔴 load-bearing**
(rate-limit correctness — bug here can quietly exceed real server budget →
ban risk. Full architect rigor, not ponytail.)

## Goal
Feed `RoundRobinTokenPool`'s per-token `RateBucketSet` the server's ground-truth
`system_info.rate_limit` (`limit`/`remaining`/`reset`/`bucket`) present in every
lzt.market response body, so local budget estimates (derived only from
`ClientConfig.general_per_min` etc.) never drift silently ahead of what the
server actually allows.

## Scope
- Parse `system_info.rate_limit` from the raw `Response.body` (already
  undropped JSON at the transport layer — `verified-by-code:src/pylzt/transport/session.py:116`
  via `_decode`, codegen only strips it from *typed* models,
  `verified-by-code:dev/codegen/generator.py:455`).
- New `RateLimitSnapshot` DTO + `.from_body()` parser (never raises — absent/
  malformed data yields `None`, pool falls back to pure estimation).
- `BaseTokenPool.report_rate_limit(...)` no-op default (mirrors
  `report_proxy`/`quarantine` convention, `verified-by-code:src/pylzt/token_pool/base.py:35`).
- `RoundRobinTokenPool` wires it to `RateBucketSet.reconcile(...)`.
- `TokenBucket.reconcile()` — **clamp-only**: `_tokens = min(_tokens, remaining)`.
  Never raises local budget above what client-side math already computed —
  server-reported *higher* remaining is ignored, only tightening is trusted.
  Design decision, `unverified` (no code settles this, it's a risk call) —
  reasoning: this repo's own queue doc tags the feature 🔴 money/ban-risk
  (`.plans/framework-utilities/01-ideas-expanded.md:18-24`); trusting the
  server to *grant* extra budget across phase-misaligned windows is the
  exact failure mode that bans an account, trusting it to *restrict* is safe.
- Call site: `RateLimitedTransport.send()` success branch, before `return resp`
  (`verified-by-code:src/pylzt/transport/rate_limited.py:70-73`).
- `ClientConfig.enable_server_rate_sync: bool = True` — fallback toggle. If
  `False`, `RateLimitedTransport` never calls `report_rate_limit` (pure
  client-side estimation, today's behavior). Required because this is a
  🔴 rate-limit-correctness path per project rules (toggle+fallback mandatory
  for load-bearing changes).
- `RateClass.ANTIPUBLIC` is out of scope — it uses `_StaticBearerPool`, a
  separate `BaseTokenPool` implementation that keeps the ABC's no-op default
  (`verified-by-code:src/pylzt/token_pool/_static.py`, confirmed by Sonnet audit).

## Non-goals
- No AIMD/adaptive concurrency (queued separately as idea #2, depends on this).
- No change to codegen / typed models — `system_info` stays untyped, parsed
  only at the transport layer from raw `resp.body`.
- No metrics/observability additions beyond what's cheap inline (deferred to
  `05-risks.md` if worth a follow-up).
- No window re-alignment logic (`reset`-driven refill-rate recalculation) —
  clamp-only per the design decision above; a fuller reconciliation is a
  separate, riskier follow-up if clamp-only proves insufficient in practice.

## Wire shape (verified against `dev/generated/openapi/lzt_market.json`)
```json
"rate_limit": {
  "type": "object",
  "required": ["limit", "remaining", "reset"],
  "properties": {
    "limit": {"type": "integer"},
    "remaining": {"type": "integer"},
    "reset": {"type": "integer"},
    "bucket": {"type": "string"}
  }
}
```
`system_info` is a required sibling field alongside the real payload in every
response schema (131 occurrences); `limit`/`remaining`/`reset` required,
`bucket` optional (absent in sampled example bodies, present in schema).
No `X-RateLimit-*` headers anywhere — strictly a body-level signal.

## Files touched
- `src/pylzt/token_pool/rate_limit.py` — **new**, `RateLimitSnapshot` DTO.
- `src/pylzt/token_pool/base.py` — add `report_rate_limit` no-op.
- `src/pylzt/token_pool/round_robin.py` — implement `report_rate_limit`.
- `src/pylzt/token_pool/bucket.py` — `TokenBucket.reconcile`,
  `RateBucketSet.reconcile` (KeyError on unknown `RateClass` → no-op, defensive
  since `ANTIPUBLIC` never reaches this pool).
- `src/pylzt/transport/rate_limited.py` — call site wiring.
- `src/pylzt/config.py` — `enable_server_rate_sync: bool = True`.
- `tests/pylzt/test_token_pool.py` — reconcile unit tests (clamp-down,
  no-op on higher remaining, malformed/absent body, unknown rate_class).
- `tests/pylzt/test_rate_limited_transport.py` — wiring test (snapshot
  parsed + forwarded on success; toggle off → never called).

## Contracts/Types (frozen)

```python
# src/pylzt/token_pool/rate_limit.py (new file)
@dataclass(frozen=True, slots=True)
class RateLimitSnapshot:
    limit: int
    remaining: int
    reset: int                    # unix epoch seconds
    bucket: str | None = None

    @classmethod
    def from_body(cls, body: dict[str, object]) -> RateLimitSnapshot | None:
        """None on absent/malformed system_info.rate_limit — never raises."""

# src/pylzt/token_pool/base.py — BaseTokenPool, add:
def report_rate_limit(
    self, token_id: TokenId, rate_class: RateClass, snapshot: RateLimitSnapshot
) -> None:
    """Reconcile local budget with server ground truth. Default no-op."""

# src/pylzt/token_pool/round_robin.py — RoundRobinTokenPool, implement:
def report_rate_limit(
    self, token_id: TokenId, rate_class: RateClass, snapshot: RateLimitSnapshot
) -> None:
    """Looks up self._buckets[token_id], delegates to RateBucketSet.reconcile.
    Unknown token_id → no-op (token may have been quarantined mid-flight)."""

# src/pylzt/token_pool/bucket.py — RateBucketSet, add:
def reconcile(
    self, rate_class: RateClass, snapshot: RateLimitSnapshot, clock: Clock
) -> None:
    """Looks up self._buckets[rate_class], delegates to TokenBucket.reconcile.
    Unknown rate_class (e.g. ANTIPUBLIC) → no-op, defensive."""

# src/pylzt/token_pool/bucket.py — TokenBucket, add:
def reconcile(self, remaining: int, clock: Clock) -> None:
    """Clamp-only: self._tokens = min(self._tokens, remaining). Never raises
    local budget. Does not touch rate/capacity/reset — refill math unchanged."""

# src/pylzt/config.py — ClientConfig, add field:
enable_server_rate_sync: bool = True
```

## Worktree
`../aiolzt-rate-limit-sync` on branch `feat/rate-limit-sync`, based on `main`.
Executor creates it (this plan does not).

## Risks / edge cases
- **Phase-misaligned windows**: server `reset` and local bucket refill cycle
  aren't synchronized. Clamp-only avoids over-granting; a future
  full-reconciliation (re-deriving refill rate from `reset`) is deferred —
  logged in `05-risks.md`.
- **Malformed/missing `system_info`** (older API version, proxy stripping
  body): `from_body` returns `None`, pool silently keeps estimating — fail
  loud only if this becomes systemic (out of scope here, single flag/metric
  is a cheap follow-up, deferred).
- **`bucket` field semantics unclear** (optional string, no docs on its
  meaning beyond a label) — stored but unused in `reconcile`; do not
  over-interpret it into extra logic this plan doesn't need.
- **Toggle default**: `enable_server_rate_sync=True` ships the sync on by
  default since it's strictly a tightening (safety) behavior — `False` is
  the escape hatch if it misbehaves in production, not the default.

## Success criteria (verifiable)
1. `RateLimitSnapshot.from_body()` correctly parses a body containing
   `system_info.rate_limit`, returns `None` for any malformed/absent shape.
2. `RoundRobinTokenPool.report_rate_limit()` clamps the matching bucket's
   `_tokens` down to `remaining` when `remaining` is lower than current
   estimate; leaves it untouched when `remaining` is higher.
3. `RateLimitedTransport.send()` calls `report_rate_limit` on every
   successful response when `enable_server_rate_sync=True`, never when
   `False`.
4. Existing `test_token_pool.py` suite (bucket drain/refill/independence,
   pool rotation/quarantine) stays green — no behavior change to the
   non-reconcile paths.
5. `RELEASE-READY` pseudo-task passes (see `04-tasks.yaml`).

## Decisions log
- **Clamp-only, not full-authority reconcile** — see Scope. `unverified`
  (risk-based design call, not settled by existing code).
- **`ANTIPUBLIC` out of scope** — `verified-by-code:src/pylzt/token_pool/_static.py`
  (separate `BaseTokenPool` impl, keeps ABC no-op default).
- **Toggle default `True`** — clamp-only is inherently safe (tightening,
  never loosening), so on-by-default is consistent with the rest of the
  pool's fail-safe posture. `unverified` (product judgment call).
- **No metrics/logging added** — kept out to stay inside module-lite budget;
  logged as deferred in `05-risks.md`.

## Code-verification (W3.5, single Sonnet audit — module-lite)
Full Sonnet audit ran against real source (not just module docs) before this
plan was drafted. All signatures above are CONFIRMED against source, including
the load-bearing feasibility question (`system_info` recoverable at transport
layer without codegen changes — CONFIRMED,
`src/pylzt/transport/base.py:46`, `src/pylzt/transport/session.py:116`).
Zero 🔴 blockers. One 🟡 correction folded in: success path in
`rate_limited.py` was previously assumed to inspect `resp.body` already — it
does not; this plan adds that inspection for the first time. No further
verification pass needed at this tier.

# auto-batching-context-manager — overview

**Tier:** module-lite · **Mode:** layered, solo, one pass

## Goal
`async with client.batching():` — concurrent `await client.execute(method)`
calls issued inside the block auto-coalesce into `/batch` requests (linger
window + chunked at `MAX_BATCH_JOBS`), reusing existing batch wire mechanics
(`build_generic_batch_request`/`parse_generic_batch_body` in `lib/batch.py`)
instead of building parallel machinery. Makes batching free instead of
opt-in-per-call (today only `Client.execute_batch(methods)` batches, and only
for an eagerly-known list).

## Scope
- New `GenericBatchCollector` in `lib/batch.py` — mirrors `BatchExecutor`'s
  internal shape (`_pending`, `_lock`, `_flush_task`, GC-guard `_tasks`,
  linger-vs-size race handling, `verified-by-code:src/pylzt/lib/batch.py:191-217`)
  but keyed by a monotonic job-id string instead of `item_id`, groups pending
  jobs by `method.__api__` before chunking (`/batch` is host-specific), reuses
  `build_generic_batch_request`/`parse_generic_batch_body`
  (`verified-by-code:src/pylzt/lib/batch.py:77-120`).
- `Client.execute()` gains exactly one `if` branch — checks a module-level
  `ContextVar[GenericBatchCollector | None]`, routes to `collector.submit(method)`
  when set (`verified-by-code:src/pylzt/client.py:258` exact current body
  confirmed: `result = self._bind(await method(self._transport_for(method)))`).
- `Client.batching(*, batch_size=MAX_BATCH_JOBS, batch_linger=0.01)` — new
  async context manager, sets the ContextVar on enter, force-flushes stragglers
  and resets on exit.
- Result routing: per-call `asyncio.Future[T]`, same pattern as
  `BatchExecutor.submit` (`verified-by-code:src/pylzt/lib/batch.py:173`).
  Server-side job failure → `BatchJobFailed(job_id, method, upstream_error)`
  (mirrors `_execute_batch_chunk`'s error shape,
  `verified-by-code:src/pylzt/client.py:234-236` — NOT `BatchExecutor`'s
  `NotFound`, which is item-id-read-specific).
- **Mixed `__api__` inside one block**: unlike `execute_batch`'s eager
  `MixedBatchApiTargets` error, `batching()` is opportunistic — silently
  groups by `__api__` into separate concurrent `/batch` calls. Design call
  (not forced by existing code), `unverified`.
- DRY fix folded in (`must-include`, cheap, in blast radius): extract
  `_method_to_job(job_id, method) -> BatchJob` shared helper in `lib/batch.py`
  — today `_execute_batch_chunk` (`client.py:207-217`) inlines this
  construction; `GenericBatchCollector._flush_group` needs the identical
  logic, so a second inline copy would violate `lib/batch.py`'s own stated
  invariant ("exactly one implementation of the wire mechanics").

## Non-goals
- No change to `Client.execute_batch()`'s existing eager-list API or its
  `MixedBatchApiTargets` strictness — that stays as-is for explicit callers.
- No `batchable`/non-batchable marker on `BaseMethod` — confirmed unnecessary,
  `execute_batch` already handles any HTTP verb via
  `request.method == GET` routing.
- No cross-task visibility — a background task spawned (not awaited) inside
  a `batching()` block inherits the ContextVar via `create_task`'s context
  copy, but if it calls `execute()` after the block's `finally` already
  flushed, its future may never resolve. Documented as a docstring warning,
  not solved (out of scope — matches asyncio's own task-lifetime contract).

## Files touched
- `src/pylzt/lib/batch.py` — `GenericBatchCollector`, `_method_to_job` helper,
  `_execute_batch_chunk` refactored to use the shared helper (fix, in blast radius).
- `src/pylzt/client.py` — module-level `_batching_var: ContextVar[...]`,
  `execute()` gains the collector-check branch, new `batching()` context manager.
- `src/pylzt/errors.py` — `BatchJobFailed(LztError)` if not already present
  (check — `_execute_batch_chunk` likely already raises something equivalent;
  reuse if so, don't fork).
- `tests/pylzt/test_batch.py` — `GenericBatchCollector` coalescing/chunking/
  linger tests (mirror existing `BatchExecutor` test shapes).
- `tests/pylzt/test_client.py` (or wherever `Client` integration tests live)
  — `batching()` context manager: concurrent `execute()` calls coalesce into
  one `/batch` call; mixed-`__api__` block produces two `/batch` calls;
  force-flush on exit picks up stragglers under the linger window.

## Contracts/Types (frozen)

```python
# src/pylzt/lib/batch.py — new
def _method_to_job(job_id: str, method: BaseMethod[Any]) -> BatchJob:
    """Shared wire-construction, single source of truth — extracted from
    Client._execute_batch_chunk's inline logic."""

class GenericBatchCollector:
    def __init__(
        self,
        transport_for: Callable[[BaseMethod[Any]], BaseTransport],
        batch_size: int,
        batch_linger: float,
        storage: BaseStorage,
    ) -> None: ...

    async def submit(self, method: BaseMethod[T]) -> T: ...
    async def _linger_flush(self) -> None: ...
    async def _do_flush(self) -> None:
        """Groups pending by method.__api__, chunks each group at
        MAX_BATCH_JOBS, gathers concurrently."""
    async def _flush_group(
        self, jobs: list[tuple[str, BaseMethod[Any], asyncio.Future[Any]]]
    ) -> None: ...

# src/pylzt/client.py
_batching_var: ContextVar[GenericBatchCollector | None] = ContextVar(
    "_batching_var", default=None
)

class Client:
    async def execute(self, method: BaseMethod[T]) -> T:
        collector = _batching_var.get()
        result = self._bind(
            await collector.submit(method) if collector is not None
            else await method(self._transport_for(method))
        )
        await self._save_media(method)
        return result

    @contextlib.asynccontextmanager
    async def batching(
        self, *, batch_size: int = MAX_BATCH_JOBS, batch_linger: float = 0.01
    ) -> AsyncIterator[None]:
        collector = GenericBatchCollector(
            self._transport_for, batch_size, batch_linger, self._batch_storage
        )
        token = _batching_var.set(collector)
        try:
            yield
        finally:
            _batching_var.reset(token)
            await collector._do_flush()

# src/pylzt/errors.py — reuse if _execute_batch_chunk already raises
# an equivalent; otherwise add:
class BatchJobFailed(LztError):
    def __init__(self, job_id: str, method: str, upstream_error: str) -> None: ...
```

## Worktree
`../aiolzt-auto-batching-context-manager` on branch `feat/auto-batching-context-manager`, based on `main`.

## Risks / edge cases
- **ContextVar isolation, not instance state**: chosen specifically because
  `Client` instances are shared across concurrent unrelated coroutines —
  instance-level "batching mode" would hijack `execute()` calls from sibling
  tasks. `ContextVar` copies into `create_task` children of the entering task,
  invisible to siblings. This is the project's existing "Context Propagation"
  pattern (see `~/.claude/library/rules/patterns.md`), not a new mechanism.
- **At-least-once vs exactly-once**: not applicable here (unlike the exporter
  plan) — batch failures surface via the per-call future's exception, caller
  sees the same error shape as a direct `execute()` call would.
- **`batch_job_history` docstring drift**: `Client.batch_job_history`
  (`client.py:157-161`) currently says "every job `execute_batch` has sent" —
  if `GenericBatchCollector` also persists via `self._batch_storage.save_jobs`
  (recommended, for audit-trail consistency with `_execute_batch_chunk`), that
  docstring needs a one-line update to cover `batching()`-issued jobs too.
- **Background-task future leak**: documented warning only (see Non-goals).

## Success criteria (verifiable)
1. Five concurrent `execute()` calls inside one `async with client.batching():`
   block produce exactly one `/batch` transport call (mirrors
   `test_five_concurrent_submits_produce_one_send_call` for `BatchExecutor`).
2. Each caller's `await client.execute(method)` still returns its own typed
   `T` — no cross-contamination between callers (mirrors
   `test_each_caller_gets_own_lot`).
3. A method whose `__api__` differs from others in the same block ends up in
   a separate `/batch` call, not an error.
4. Exiting the block force-flushes any pending sub-linger-window jobs — no
   dropped calls.
5. `Client.execute_batch()`'s existing eager-list behavior (including
   `MixedBatchApiTargets`) is unchanged — full existing `test_client.py`/
   `test_batch.py` suites stay green.

## Decisions log
- **ContextVar over instance state** — `verified-by-code:src/pylzt/client.py`
  (Client is shared across coroutines; project pattern catalogue names
  "Context Propagation" explicitly).
- **Silent per-`__api__` grouping over eager `MixedBatchApiTargets` error** —
  `unverified` (design call; `batching()` is opportunistic/implicit, unlike
  `execute_batch`'s explicit list).
- **`_method_to_job` extraction folded in as `must-include`** —
  `verified-by-code:src/pylzt/client.py:207-217` (inline duplication would
  violate `lib/batch.py`'s own single-implementation invariant, cheap and in
  blast radius).

## Code-verification (W3.5, single Sonnet audit — module-lite)
Full Sonnet audit ran against real source. Corrected 4 stale line numbers from
the Haiku pass (`__aenter__`/`__aexit__` at `client.py:292/295` not 360/363;
`_transport_for` at 126 not 151; `execute` at 258 not 319; `execute_batch`/
`_execute_batch_chunk` at 189/205 not 227/248) — folded into this doc's
`verified-by-code` cites above. Confirmed `execute()`'s exact current body
(no existing hook) and confirmed no `batchable` marker exists on `BaseMethod`.
Zero 🔴 blockers. Two 🟡 design calls flagged above (mixed-`__api__` grouping,
`_method_to_job` extraction) — both resolved and folded into contracts.

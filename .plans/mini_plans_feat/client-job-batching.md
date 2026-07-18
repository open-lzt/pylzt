## Goal
Explicit per-call batching (`await client.job(method)`), AS7-style convenience, without requiring
the caller to wrap calls in `async with client.batching(): ...`.

## Touch
- `src/pylzt/client.py` — new `Client.job()` method + `_default_collector` field + `aclose()` cleanup.
- `tests/pylzt/test_client_batching.py` — new tests for `job()` (standalone + inside `batching()`).

## Contracts/Types
No new DTOs. Signature: `async def job[T](self, method: BaseMethod[T]) -> T` — same shape as
`execute()`, reuses `GenericBatchCollector` (existing type). `self._default_collector:
GenericBatchCollector | None = None` — lazily created on first `job()` call outside a `batching()`
scope, persists for the client's lifetime, reused across all standalone `job()` calls so they
coalesce with each other even without an explicit `batching()` block.

## Approach
1. `Client.__init__` — add `self._default_collector: GenericBatchCollector | None = None`.
2. `Client.job(method)` — if `_batching_var` (ambient collector from an active `batching()` block)
   is set, submit into it (matches `execute()`'s coalescing there). Otherwise lazily create/reuse
   `self._default_collector` and submit into it — so `job()` calls anywhere coalesce with each
   other by default, no context manager needed. `_bind` the result same as `execute()`.
3. `Client.aclose()` — if `self._default_collector` is not None, flush it (`await
   self._default_collector._do_flush()`) before closing transports, so no job silently hangs.
4. Docstring cross-reference on `execute()`/`batching()` pointing to `job()` as the no-block alternative.

## Risk/edge
Concurrent `job()` calls across different `__api__` targets (market+forum) already handled by
`GenericBatchCollector`'s per-target grouping — no new risk. `_default_collector` is never reset
mid-life (unlike `batching()`'s scoped one), so pending jobs across arbitrarily-spaced `job()` calls
still coalesce by the existing `batch_size`/`batch_linger` window.

## Test
`test_client_batching.py`: two concurrent `job()` calls (no `batching()` block) hit `/batch` once,
not twice; a `job()` call inside an active `batching()` block shares that scope's collector.

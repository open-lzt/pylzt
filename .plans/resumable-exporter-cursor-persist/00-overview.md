# resumable-exporter-cursor-persist — overview

**Tier:** module-lite · **Mode:** layered, solo, one pass

## Goal
A long-running export persists its pagination cursor to a new `BaseCursorStorage`
seam so a crash mid-export resumes from the last checkpoint instead of
restarting from page 1. No exporter/bulk-export utility exists yet in this
repo (round-1 "bulk-экспортёр" idea was never built) — this plan builds the
resume-capable primitive that would underpin it.

## Scope
- `Page[T]` confirmed: `@dataclass(frozen=True, slots=True)` with exactly
  `items: Sequence[T]`, `has_more: bool` — no cursor/token field
  (`verified-by-code:src/pylzt/pagination.py`). lzt.market's real
  pagination is integer `page`/`perPage` query params only, no opaque
  cursor string anywhere in the OpenAPI spec — `Paginator`'s int-page model
  is a correct fit, no hidden cursor semantics being missed.
- `BaseStorage` (`lib/storage.py`) is confirmed **not generic** — every
  abstract method is hardcoded to `BatchJobRecord`, and `commit_jobs`'s
  status-flip semantics don't fit a cursor (a cursor is overwritten, not
  committed). This repo's convention is **one ABC per persisted concept**
  (`BaseCache[T]`, `BaseMediaStorage`, `BaseStorage` — each own file/shape),
  confirmed across `cache.py`/`media_storage.py`/`storage.py`. A cursor is a
  fourth distinct concept → new sibling ABC, own file (`storage.py` is
  already batch-job-specific in its module docstring; new file keeps
  one-concept-per-file per project-structure rules).
- `Paginator` (`pagination.py`) has **zero accessors** on its private
  `_fetch`/`_start`/`_max_pages` and its loop-local `page`/`walked` — cannot
  compose a resumable wrapper *around* an existing instance, nothing to
  observe. Resolved: one small additive, backward-compatible hook parameter
  `on_page_start: Callable[[int], Awaitable[None]] | None = None`, called
  **before** each page fetch (checkpoint-before-fetch = at-least-once resume:
  a crash mid-page re-fetches that whole page rather than silently skipping
  its items — consistent with `lib/storage.py`'s own `commit_jobs`/
  `only_pending` posture of "re-process over silent loss").
- `ResumableExporter[T]` — new class (own module, not `Paginator` subclass)
  wrapping a `fetch` callable + `BaseCursorStorage`: loads a saved cursor on
  `__aiter__` start, checkpoints via `on_page_start` before each page,
  clears the cursor only on natural exhaustion (early `break` by the caller
  correctly leaves the cursor in place for a future resume).

## Non-goals
- No change to `BaseStorage`/`BatchJobRecord` — cursor persistence is a
  separate ABC, not bolted onto the batch-job seam.
- No opaque-cursor-token support — lzt.market's real API is integer-page
  only; building token support now would be speculative (YAGNI).
- No exactly-once guarantee — at-least-once (documented, see Risks). A
  stricter guarantee would need per-item dedup state, out of scope here.
- No CLI/bulk-export command built on top of `ResumableExporter` — this plan
  ships the resumable primitive only; a CLI wrapper is a follow-up if the
  round-1 "bulk-экспортёр" idea gets picked up.

## Files touched
- `src/pylzt/pagination.py` — additive `on_page_start` param on
  `Paginator.__init__`, invoked in `__aiter__` before `await self._fetch(page)`.
- `src/pylzt/lib/cursor_storage.py` — **new**, `ExportCursor`,
  `BaseCursorStorage`, `MemoryCursorStorage`.
- `src/pylzt/export/resumable_exporter.py` — **new** (new `export/`
  package — namable in one sentence, domain-free wrt host entities, but
  this IS the second call site the isolation rule wants before extracting
  to `libs/`; stays inline under `src/pylzt/export/` for now since it
  depends on `Paginator`/`Page[T]` which are host-package types, not
  domain-free per the `libs/` criteria).
- `tests/pylzt/test_pagination.py` — **new** (no existing tests for
  `Paginator` — confirmed gap), covers `on_page_start` hook firing
  before-fetch, backward-compat (param omitted → unchanged behavior).
- `tests/pylzt/test_cursor_storage.py` — **new**, `MemoryCursorStorage`
  save/load/clear round-trip.
- `tests/pylzt/test_resumable_exporter.py` — **new**, resume-after-crash
  simulation, clear-on-exhaustion, no-clear-on-early-break.

## Contracts/Types (frozen)

```python
# src/pylzt/pagination.py — additive, backward-compatible
class Paginator[T]:
    def __init__(
        self,
        fetch: Callable[[int], Awaitable[Page[T]]],
        *,
        start_page: int = 1,
        max_pages: int | None = None,
        on_page_start: Callable[[int], Awaitable[None]] | None = None,  # NEW
    ) -> None: ...
    # __aiter__: calls `await self._on_page_start(page)` (if set) BEFORE
    # `await self._fetch(page)`, on every iteration — checkpoint-before-fetch.

# src/pylzt/lib/cursor_storage.py — new file
@dataclass(frozen=True, slots=True)
class ExportCursor:
    export_id: str
    next_page: int
    walked: int = 0   # cumulative pages consumed across resumes, observability only

class BaseCursorStorage(ABC):
    @abstractmethod
    async def save_cursor(self, cursor: ExportCursor) -> None:
        """Upsert — overwrites any existing cursor for cursor.export_id."""
    @abstractmethod
    async def load_cursor(self, export_id: str) -> ExportCursor | None: ...
    @abstractmethod
    async def clear_cursor(self, export_id: str) -> None:
        """Call only on natural exhaustion."""

class MemoryCursorStorage(BaseCursorStorage):
    def __init__(self) -> None: ...

# src/pylzt/export/resumable_exporter.py — new module
class ResumableExporter[T]:
    def __init__(
        self,
        export_id: str,
        fetch: Callable[[int], Awaitable[Page[T]]],
        storage: BaseCursorStorage,
        *,
        max_pages: int | None = None,
    ) -> None: ...

    async def __aiter__(self) -> AsyncIterator[T]:
        """Loads saved cursor (resume) or starts at page 1 (fresh). Wraps a
        Paginator with on_page_start=checkpoint. Clears the cursor only if
        the async for fully drains (natural exhaustion) — early break by the
        caller leaves the cursor for a future resume."""
```

## Worktree
`../aiolzt-resumable-exporter-cursor-persist` on branch `feat/resumable-exporter-cursor-persist`, based on `main`.

## Risks / edge cases
- **At-least-once, not exactly-once**: checkpoint written before fetching a
  page → a crash mid-page re-fetches and re-yields that page's items on
  resume. Downstream consumers must dedupe by item id or tolerate
  boundary-page duplicates. Consistent with the codebase's existing
  idempotency posture (`commit_jobs`/`only_pending` in `lib/storage.py`),
  not a new risk class — documented, not solved further here.
- **`export_id` collision**: two concurrent exports with the same
  `export_id` would clobber each other's cursor (`save_cursor` is an
  upsert). Caller's responsibility to pick a unique id — cheap guard
  (`unverified` whether worth an explicit uniqueness check inside
  `MemoryCursorStorage`; deferred, YAGNI until a real collision surfaces).
- **`_MODULE_AUTO.md` staleness** (pre-existing, unrelated): `lib/`'s doc
  shows `get_jobs()` with no params, real signature has `only_pending`/
  `limit`/`offset`. Flagged for a separate `/docskill` pass, not blocking
  this plan — RELEASE-READY still regenerates `lib/_MODULE_AUTO.md` as part
  of this plan's own touched-package doc sync, which will incidentally fix it.

## Success criteria (verifiable)
1. `Paginator` with `on_page_start` set fires the hook before every fetch,
   in order; omitting the param leaves existing behavior unchanged (backward
   compat — existing `Paginator` call sites, if any, need zero changes).
2. `ResumableExporter` resumes from the last saved `next_page` after a
   simulated crash (kill mid-iteration, re-instantiate, re-iterate — picks
   up from the checkpoint, not page 1).
3. `clear_cursor` is called exactly once, only when the `async for` fully
   drains; an early `break` leaves the cursor saved.
4. `MemoryCursorStorage` round-trips `ExportCursor` correctly (save → load
   → matches; clear → load → `None`).
5. `RELEASE-READY` pseudo-task passes.

## Decisions log
- **New sibling ABC (`BaseCursorStorage`), not `BaseStorage` reuse** —
  `verified-by-code:src/pylzt/lib/storage.py` (hardcoded to
  `BatchJobRecord`, wrong domain type; one-ABC-per-concept is this repo's
  established convention).
- **Additive `on_page_start` hook over a duplicate loop** —
  `verified-by-code:src/pylzt/pagination.py` (Paginator has zero
  accessors; forking the fetch/yield/stop loop would violate DRY / single
  source of truth for pagination logic).
- **`export/` package, not `libs/`** — `unverified`-adjacent judgment call:
  depends on host-package types (`Page[T]`), fails the `libs/`
  domain-free criterion even though it's namable in one sentence.
- **Checkpoint-before-fetch (at-least-once)** — `verified-by-code:src/pylzt/lib/storage.py`
  (mirrors the codebase's existing crash-safety posture in `BatchJobRecord`/
  `commit_jobs`, not inventing a new risk model).

## Code-verification (W3.5, single Sonnet audit — module-lite)
Full Sonnet audit ran against real source. Confirmed `Page[T]`'s exact two
fields (Haiku hadn't described them), confirmed the real lzt.market
pagination shape (integer page params only, via the committed OpenAPI spec),
confirmed `BaseStorage`'s non-genericity, confirmed zero existing
cursor/resume/checkpoint code anywhere (grep hits were false positives:
`CURSOR_*` product-tier enum members, unrelated `_cursor` round-robin
indices). Zero 🔴 blockers. One pre-existing unrelated doc-staleness note
folded into Risks (not this plan's defect).

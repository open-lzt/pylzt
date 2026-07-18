# Plan queue

Tracks follow-up `/swarm-plan` runs the user asked to defer, so they aren't lost.

## Pending

(empty — all queued ideas landed 2026-07-07)

## Done

- **media-upload** — landed. `Media` type, `Request.files`, multipart wiring,
  `BaseMediaStorage`/`NullMediaStorage`, codegen `format: binary` -> `Media` detection.
- **api-namespaces** — landed (T1-T14, merged into `main`). `client.market`/`.forum`/
  `.antipublic` namespaces, AntiPublic API target (`antipublic.one/api/v2`, 8
  endpoints, `_StaticBearerPool`), codegen sync-facade rendering, `SyncClient`.
- **rate-limit-sync** — landed (`.plans/rate-limit-sync/`, merged into `main`).
  `RateLimitSnapshot` DTO, `BaseTokenPool.report_rate_limit`, `TokenBucket`/
  `RateBucketSet.reconcile` (clamp-only), wired from `RateLimitedTransport`'s
  success branch. `ClientConfig.enable_server_rate_sync=True`. = idea **#1**.
- **spec-drift-ci-checker** — landed (`.plans/mini_plans_feat/spec-drift-ci-checker.md`,
  merged into `main`). `python -m dev.codegen diff` scrapes a fresh spec to a
  tempdir, diffs against the committed `dev/generated/openapi/lzt_*.json`,
  exit 1 on drift. = idea **#7**.
- **auto-batching-context-manager** — landed (`.plans/auto-batching-context-manager/`,
  merged into `main`). `async with client.batching():` via a module-level
  `ContextVar` + `GenericBatchCollector` in `lib/batch.py`; `Client.execute()`
  gains a one-`if` collector-check branch. Extracted `_method_to_job` as the
  single method->wire-job implementation, shared with `_execute_batch_chunk`.
  = idea **#12**.
- **resumable-exporter-cursor-persist** — landed (`.plans/resumable-exporter-cursor-persist/`,
  merged into `main`). New `BaseCursorStorage`/`ExportCursor` + additive
  `Paginator.on_page_start` hook + `ResumableExporter` (at-least-once resume,
  checkpoint-before-fetch). = idea **#13**.
- **entry-points-plugin-discovery** — landed (`.plans/entry-points-plugin-discovery/`,
  merged into `main`). New `plugins.py` (`discover_middlewares`/`discover_metrics`
  via `importlib.metadata`), wired at `Client.__init__`. Explicit `metrics=` arg
  always wins; 2+ discovered metrics plugins raises `AmbiguousPlugin`. = idea **#20**.
- **adaptive-concurrency-governor** — landed (`.plans/adaptive-concurrency-governor/`,
  merged into `main`). New `AdaptiveGate` primitive (`lib/concurrency.py`,
  hand-rolled resizable semaphore) + `AimdConcurrencyGovernor` hooked into
  `RateLimitedTransport` as its own gate per `RateClass` — deliberately not
  the existing proxy-pool `asyncio.Semaphore` bulkheads (different invariant).
  `ClientConfig.enable_adaptive_concurrency=False` (opt-in). = idea **#2**.

All 6 ideas from `.plans/framework-utilities/01-ideas-expanded.md` round 2 are
now built. See that file for context on any follow-on ideas (round 2 axes B/D/F/G/H
weren't queued — pick from there if more framework-utility work is wanted).

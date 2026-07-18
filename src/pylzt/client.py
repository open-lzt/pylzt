"""`Client` — the SDK facade. DI ctor, per-ApiTarget rate-limited transports.

Owns no request loop itself: lease → sign → transport → retry/report lives in
`BaseTransport.send()` (a template method), so each `HttpxSession` built here is
already rate-limited — one per `ApiTarget` (market/forum share `token_pool`;
antipublic gets its own `_StaticBearerPool`). Domain methods live on the attached
`.market`/`.forum`/`.antipublic` namespaces (`facades/_namespace.py`), not on
`Client` itself — it is a `@final` composition root, not an extension point.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator, Sequence
from contextvars import ContextVar
from typing import Any, final

from pylzt.config import ClientConfig
from pylzt.errors import (
    BatchJobFailed,
    CredentialMissing,
    MethodDeclarationError,
    MixedBatchApiTargets,
)
from pylzt.facades._namespace import AntipublicNamespace, ForumNamespace, MarketNamespace
from pylzt.lib.asyncio_utils import gather_or_raise
from pylzt.lib.batch import (
    MAX_BATCH_JOBS,
    GenericBatchCollector,
    _method_to_job,
    build_generic_batch_request,
    parse_generic_batch_body,
)
from pylzt.lib.cache import BaseCache, MemoryCache
from pylzt.lib.clock import Clock, RealClock
from pylzt.lib.media_storage import BaseMediaStorage, NullMediaStorage
from pylzt.lib.metrics import BaseMetrics, NullMetrics
from pylzt.lib.retry import BaseRetryPolicy, ExponentialBackoff
from pylzt.media import Media
from pylzt.methods.base import BaseMethod
from pylzt.models.base import BoundModel
from pylzt.models.category import FilterSchema
from pylzt.pagination import Page
from pylzt.plugins import discover_metrics, discover_middlewares
from pylzt.proxy_pool.base import BaseProxySource
from pylzt.proxy_pool.sticky import NullProxyPool, StickyProxyPool
from pylzt.storage import BaseStorage, BatchJobRecord, MemoryStorage
from pylzt.token_pool._static import _StaticBearerPool
from pylzt.token_pool.base import BaseTokenPool, Token
from pylzt.token_pool.governor import (
    AimdConcurrencyGovernor,
    BaseConcurrencyGovernor,
    NullConcurrencyGovernor,
)
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.transport.middleware import BaseMiddleware
from pylzt.transport.session import HttpxSession
from pylzt.types import ApiTarget, RateClass, TokenId

# Set only while inside `async with client.batching():` — execute() routes through
# the collector when present. ContextVar (not instance state) because Client is
# shared across concurrent unrelated coroutines; a ContextVar is copied into
# create_task children of the entering task but invisible to sibling tasks on
# the same Client.
_batching_var: ContextVar[GenericBatchCollector | None] = ContextVar("_batching_var", default=None)

# Default linger window shared by `batching()`'s own default and `job()`'s lazily-created
# collector — one literal, not two independently-tunable copies that could silently drift.
_DEFAULT_BATCH_LINGER = 0.01


def _as_tokens(tokens: Sequence[str | Token]) -> list[Token]:
    return [
        t if isinstance(t, Token) else Token(token_id=TokenId(f"tok{i}"), credential=t)
        for i, t in enumerate(tokens)
    ]


@final
class Client:
    """Catalog read client. Zero I/O at import; all I/O is awaited on a method.

    Composition root, not an extension point: builds one rate-limited
    `HttpxSession` per `ApiTarget` (market/forum share `token_pool`; antipublic
    gets its own `_StaticBearerPool`, see Decisions in
    `.plans/api-namespaces/00-overview.md`) and attaches
    `.market`/`.forum`/`.antipublic` namespaces — see `facades/_namespace.py`.
    Never inherits a generated facade base.
    """

    def __init__(
        self,
        tokens: Sequence[str | Token] | None = None,
        *,
        antipublic_key: str | None = None,
        transport: BaseTransport | None = None,
        forum_transport: BaseTransport | None = None,
        antipublic_transport: BaseTransport | None = None,
        token_pool: BaseTokenPool | None = None,
        proxy_source: BaseProxySource | None = None,
        retry: BaseRetryPolicy | None = None,
        metrics: BaseMetrics | None = None,
        clock: Clock | None = None,
        category_cache: BaseCache[FilterSchema] | None = None,
        batch_storage: BaseStorage | None = None,
        media_storage: BaseMediaStorage | None = None,
        config: ClientConfig | None = None,
    ) -> None:
        self.config = config or ClientConfig()
        self._clock = clock or RealClock()
        self._plugin_middlewares: tuple[BaseMiddleware, ...] = (
            discover_middlewares() if self.config.enable_plugin_discovery else ()
        )
        self._metrics = metrics or (
            (discover_metrics() if self.config.enable_plugin_discovery else None) or NullMetrics()
        )
        self._concurrency_governor: BaseConcurrencyGovernor = (
            AimdConcurrencyGovernor(metrics=self._metrics)
            if self.config.enable_adaptive_concurrency
            else NullConcurrencyGovernor()
        )
        self._retry = retry or ExponentialBackoff()
        self._category_cache = category_cache or MemoryCache(clock=self._clock)
        self._batch_storage = batch_storage or MemoryStorage()
        self._media_storage = media_storage or NullMediaStorage()
        # Lazily created on the first standalone `job()` call (see `job()`) — persists for the
        # client's lifetime so unrelated `job()` calls anywhere still coalesce with each other,
        # unlike `batching()`'s scoped collector which only lives for its own `async with` block.
        self._default_collector: GenericBatchCollector | None = None
        if token_pool is not None:
            self._token_pool = token_pool
        else:
            if not tokens:
                raise ValueError("Client needs tokens or an explicit token_pool")
            proxy_pool = (
                StickyProxyPool(proxy_source, clock=self._clock)
                if proxy_source is not None
                else NullProxyPool()
            )
            self._token_pool = RoundRobinTokenPool(
                _as_tokens(tokens),
                proxy_pool=proxy_pool,
                clock=self._clock,
                general_per_min=self.config.general_per_min,
                search_per_min=self.config.search_per_min,
                forum_per_min=self.config.forum_per_min,
                metrics=self._metrics,
            )
        self._transport = transport or self._raw_transport(self.config.base_url, self._token_pool)
        self._forum_transport = forum_transport or self._raw_transport(
            self.config.forum_base_url, self._token_pool
        )
        # AntiPublic is never fungible with the market/forum fleet (a license key, not
        # an OAuth token) — no dedicated transport is built without a key; a call
        # through `.antipublic` in that state raises CredentialMissing (_transport_for).
        self._antipublic_transport: BaseTransport | None = None
        if antipublic_key is not None:
            antipublic_pool = _StaticBearerPool(
                key=antipublic_key, per_min=self.config.antipublic_per_min, clock=self._clock
            )
            self._antipublic_transport = antipublic_transport or self._raw_transport(
                self.config.antipublic_base_url, antipublic_pool
            )
        self.market = MarketNamespace(self)
        self.forum = ForumNamespace(self)
        self.antipublic = AntipublicNamespace(self)

    def _raw_transport(self, base_url: str, pool: BaseTokenPool) -> BaseTransport:
        return HttpxSession(
            base_url=base_url,
            timeout=self.config.request_timeout,
            middlewares=self._plugin_middlewares,
            token_pool=pool,
            retry=self._retry,
            metrics=self._metrics,
            clock=self._clock,
            enable_server_rate_sync=self.config.enable_server_rate_sync,
            concurrency_governor=self._concurrency_governor,
        )

    def _transport_for(self, method: BaseMethod[Any]) -> BaseTransport:
        match method.__api__:
            case ApiTarget.MARKET:
                return self._transport
            case ApiTarget.FORUM:
                return self._forum_transport
            case ApiTarget.ANTIPUBLIC:
                if self._antipublic_transport is None:
                    raise CredentialMissing("antipublic_key")
                return self._antipublic_transport
            case _:
                # Defensive: today `ApiTarget` has exactly these 3 members (mypy proves
                # the match exhaustive) — this only fires if a future member is added
                # here without a matching case, and turns that into a loud typed error
                # instead of `method(None)` raising an opaque AttributeError downstream.
                raise MethodDeclarationError(
                    type(method).__name__, f"unrouted __api__={method.__api__!r}"
                )

    def reconfigure(self, *, token_pool: BaseTokenPool | None = None) -> None:
        """Hot-swap the live token pool (account/proxy rotation) — no restart needed.

        Narrower than replacing a whole transport (library-design Law 28): retry policy,
        metrics, and clock stay put on both transports; only the pool they lease from
        changes. An in-flight `lease()` already holds its own reference and completes
        against the old pool; the next `send()` call picks up the new one.
        """
        if token_pool is not None:
            self._token_pool = token_pool
            self._transport.set_token_pool(token_pool)
            self._forum_transport.set_token_pool(token_pool)

    async def batch_job_history(
        self, *, only_pending: bool = False, limit: int | None = None, offset: int = 0
    ) -> list[BatchJobRecord]:
        """Every job `execute_batch` has sent + its outcome, oldest first, paginated by
        `limit`/`offset` — reads through to the injected `BaseStorage` (in-process and
        lost on restart unless a real one was passed to `batch_storage=`). Defaults to
        the full audit view (`only_pending=False`); pass `True` to see only records
        `commit_batch_jobs` hasn't acknowledged yet (the same filter
        `iter_pending_batch_jobs` consumes)."""
        return await self._batch_storage.get_jobs(
            only_pending=only_pending, limit=limit, offset=offset
        )

    async def commit_batch_jobs(self, record_ids: Sequence[str]) -> None:
        """Acknowledge `record_ids` (from `BatchJobRecord.record_id`) — they stop
        appearing under `only_pending=True` but stay in storage for audit. Safe to
        call again with the same ids after a crash mid-consume-loop."""
        await self._batch_storage.commit_jobs(record_ids)

    async def delete_batch_jobs(self, record_ids: Sequence[str]) -> None:
        """Hard-remove `record_ids` from storage — explicit retention/cleanup,
        independent of commit state."""
        await self._batch_storage.delete_jobs(record_ids)

    async def iter_pending_batch_jobs(
        self, *, poll_interval: float = 1.0, page_size: int = 50, stop_when_empty: bool = False
    ) -> AsyncIterator[BatchJobRecord]:
        """Consume-commit loop over not-yet-committed `execute_batch` records: pull a
        page, yield each one, commit it once the caller's loop body resumes (so a body
        that raises leaves that record uncommitted — it comes back on the next poll,
        at-least-once, never silently dropped). Polls every `poll_interval` seconds
        while storage is empty; pass `stop_when_empty=True` to drain once and return
        instead of waiting forever (useful for tests / one-shot batch processing)."""
        while True:
            page = await self._batch_storage.get_jobs(only_pending=True, limit=page_size)
            if not page:
                if stop_when_empty:
                    return
                await asyncio.sleep(poll_interval)
                continue
            for record in page:
                yield record
                await self._batch_storage.commit_jobs([record.record_id])

    async def execute_batch[T](self, methods: Sequence[BaseMethod[T]]) -> list[T]:
        """Run N heterogeneous `BaseMethod` calls through POST /batch instead of N
        separate requests — chunked at `MAX_BATCH_JOBS`, chunks run concurrently, results
        come back typed and in input order (each method's own `parse_response` decodes
        its slice of the batch response, so a mixed batch of different endpoint types
        works — no need for every job to be the same method).

        Every method must share one `__api__` (`/batch` is host-specific: market XOR
        forum) — mixing raises `MixedBatchApiTargets`, since this list is explicit and
        hand-curated by the caller (contrast `batching()`, which groups by `__api__`
        instead of raising, since its calls arrive implicitly from wherever the block's
        body happens to call `execute()`). A job that errors server-side raises
        `BatchJobFailed` naming its method + upstream message, failing the whole call
        rather than silently dropping a result the caller explicitly asked for.
        """
        if not methods:
            return []
        targets = frozenset(method.__api__ for method in methods)
        if len(targets) > 1:
            raise MixedBatchApiTargets(targets=frozenset(t.value for t in targets))
        chunks = [methods[i : i + MAX_BATCH_JOBS] for i in range(0, len(methods), MAX_BATCH_JOBS)]
        chunk_results = await gather_or_raise(self._execute_batch_chunk(chunk) for chunk in chunks)
        return [result for chunk in chunk_results for result in chunk]

    async def _execute_batch_chunk[T](self, methods: Sequence[BaseMethod[T]]) -> list[T]:
        # Job ids are 1-indexed, not 0-indexed: verified live that the server treats
        # id "0" as empty (a PHP/XenForo-side `empty("0") == true` quirk) and silently
        # falls back to keying that job's result by its uri instead of the id we sent.
        jobs = [_method_to_job(str(i + 1), method) for i, method in enumerate(methods)]
        rate_class = RateClass.FORUM if methods[0].__api__ is ApiTarget.FORUM else RateClass.GENERAL
        response = await self._transport_for(methods[0]).send(
            build_generic_batch_request(jobs, rate_class=rate_class)
        )
        results = parse_generic_batch_body(response.body)

        # Persist before raising — a failed job still belongs in the audit trail, not
        # just the ones that happened to succeed. record_id is a fresh uuid, not job.id:
        # job.id is only unique within this one chunk (1-indexed per call, reused across
        # calls), so it can't double as storage's cross-call primary key.
        await self._batch_storage.save_jobs(
            [
                BatchJobRecord(record_id=uuid.uuid4().hex, job=job, result=results.get(job.id))
                for job in jobs
            ]
        )

        out: list[T] = []
        for i, method in enumerate(methods):
            entry = results.get(str(i + 1))
            if entry is None or not entry.ok:
                raise BatchJobFailed(
                    job_id=str(i + 1),
                    method=type(method).__name__,
                    upstream_error=entry.error if entry is not None else None,
                )
            item = entry.item if isinstance(entry.item, dict) else {}
            out.append(method.parse_response(Response(status=200, body=item)))
        return out

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        rate_class: RateClass = RateClass.GENERAL,
    ) -> Response:
        """Escape hatch: call ANY market endpoint through the rate-limited rail.

        Builds a `Request` and runs it through the same lease → sign → retry →
        typed-error pipeline as the typed read methods, returning the decoded
        `Response`. Use for endpoints the SDK does not wrap yet: you keep the token
        pool, rate limiting, retries and typed errors; you lose the per-endpoint DTO.
        """
        return await self._transport.send(
            Request(
                method=method,
                path=path,
                rate_class=rate_class,
                query=query or {},
                json_body=json_body,
            )
        )

    async def execute[T](self, method: BaseMethod[T]) -> T:
        """Run a method-as-class through the rail matching its `__api__` and bind the result.

        Inside `async with client.batching():`, coalesces with concurrent `execute()`
        calls into `/batch` requests instead of one request per call — see `batching()`.
        For a single call you want batched without opening a block, see `job()`.
        """
        collector = _batching_var.get()
        result = (
            await collector.submit(method)
            if collector is not None
            else await method(self._transport_for(method))
        )
        return await self._after_call(method, result)

    async def job[T](self, method: BaseMethod[T]) -> T:
        """AS7-style per-call batching — no `async with client.batching():` block needed.

        Inside an active `batching()` scope, behaves exactly like `execute()` (shares that
        scope's collector). Outside one, coalesces with every other standalone `job()` call
        made through this client via one shared, lazily-created collector that persists for
        the client's lifetime — so two unrelated `job()` calls issued concurrently anywhere
        still merge into one `/batch` request instead of each firing its own throwaway window.
        """
        collector = _batching_var.get()
        if collector is None:
            if self._default_collector is None:
                self._default_collector = GenericBatchCollector(
                    self._transport_for,
                    MAX_BATCH_JOBS,
                    _DEFAULT_BATCH_LINGER,
                    self._batch_storage,
                )
            collector = self._default_collector
        result = await collector.submit(method)
        return await self._after_call(method, result)

    async def _after_call[T](self, method: BaseMethod[T], result: T) -> T:
        """Shared tail for every single-method execution path (`execute()`, `job()`) —
        saves any `Media` the method carried and binds the client to the result. One
        call site instead of duplicating both steps at every entry point; `execute_batch()`
        goes through `_method_to_job` instead, which raises `MediaNotBatchable` up front for
        a Media-bearing method rather than silently dropping the file — /batch's flat job
        format has no multipart slot to carry it."""
        await self._save_media(method)
        return self._bind(result)

    async def _save_media(self, method: BaseMethod[Any]) -> None:
        """Best-effort cache of any `Media` fields on a successfully-executed method.
        A broken custom storage impl must never turn a successful upload into a
        client-visible error — the call already returned 2xx by the time this runs."""
        for name in type(method).model_fields:
            value = getattr(method, name)
            if isinstance(value, Media):
                with contextlib.suppress(Exception):
                    await self._media_storage.save(value.sha256, value)

    @contextlib.asynccontextmanager
    async def batching(
        self, *, batch_size: int = MAX_BATCH_JOBS, batch_linger: float = _DEFAULT_BATCH_LINGER
    ) -> AsyncIterator[None]:
        """Concurrent `execute()` calls issued inside this block auto-coalesce into
        `/batch` requests (windowed by `batch_linger`, chunked at `MAX_BATCH_JOBS`,
        grouped by `__api__`) instead of one request per call. Grouping by `__api__`
        instead of raising is deliberate here (contrast `execute_batch()`, whose
        explicit hand-curated list raises `MixedBatchApiTargets` on a mix) — calls
        inside this block arrive implicitly from wherever the body happens to call
        `execute()`, so a mixed market/forum call is expected, not a caller bug.
        Only calls `await`ed from inside the block are guaranteed to be captured — a
        background task spawned (not awaited) here may call `execute()` after the
        block's flush. For batching a single call without a block, see `job()`.
        """
        collector = GenericBatchCollector(
            self._transport_for, batch_size, batch_linger, self._batch_storage
        )
        token = _batching_var.set(collector)
        try:
            yield
        finally:
            _batching_var.reset(token)
            await collector._do_flush()

    async def __call__[T](self, method: BaseMethod[T]) -> T:
        """Callable shorthand for `execute` — generated facades run `self(Method(...))`."""
        return await self.execute(method)

    def _bind[R](self, result: R) -> R:
        """Attach self to any `BoundModel` in the result so `lot.refresh()` works."""
        if isinstance(result, BoundModel):
            result.as_(self)
        elif isinstance(result, Page):
            for item in result.items:
                if isinstance(item, BoundModel):
                    item.as_(self)
        elif isinstance(result, list):
            for item in result:
                if isinstance(item, BoundModel):
                    item.as_(self)
        return result

    async def aclose(self) -> None:
        if self._default_collector is not None:
            # Flush any jobs `job()` queued but hadn't yet coalesced — otherwise their
            # awaiting callers would hang past this client's own lifetime.
            await self._default_collector._do_flush()
        await self._transport.aclose()
        await self._forum_transport.aclose()
        if self._antipublic_transport is not None:
            await self._antipublic_transport.aclose()
        await self._token_pool.aclose()

    async def __aenter__(self) -> Client:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

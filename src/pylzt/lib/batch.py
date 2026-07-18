"""Request-coalescing batch primitive for lzt.market's/lolz.live's shared /batch endpoint.

`BatchExecutor.submit(item_id)` looks like a single-item read to the caller but
internally groups concurrent submissions and flushes them as POST /batch
request(s) — either when `batch_size` items are queued or after the
`batch_linger` window expires (whichever fires first). Each outgoing POST
still carries at most `MAX_BATCH_JOBS` jobs (the server-enforced hard cap), so
a flush past that count spans multiple concurrent requests/leases, not one.

Real wire shape, verified live 2026-07-03 against prod-api.lzt.market:
- Request: POST /batch with a **flat JSON array** (not a `{"requests": [...]}}`
  envelope) of `{"id": "<id>", "method": "GET", "uri": "/<item_id>", "params": {}}`.
- Response: `{"jobs": {"<id>": {"_job_result": "ok", "item": {...}}}}` per hit,
  `{"_job_result": "error", "_job_error": "<message>"}` per miss/failure.
- The server rejects anything over 10 jobs in one request with
  `400 {"errors": ["Maximum batch jobs is 10"]}` — `MAX_BATCH_JOBS` below.

`build_generic_batch_request`/`parse_generic_batch_body` expose that same wire shape for
ARBITRARY job specs (any method/uri/params, not just lot-id GETs) —
`methods/market_batch_requests.Batch` and `methods/forum_batch_requests.BatchExecute`
(both hand-patched; the codegen'd versions had no request-body fields at all, since the
OpenAPI spec's "array of job objects" body shape isn't a flat field set codegen's method
generator can capture) build on these directly. `_build_batch_request`/`_parse_batch_body`
(the lot-specific pair `catalog.GetLotsBatch` uses) are themselves thin wrappers over the
generic pair, so there is exactly one implementation of the wire mechanics.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from pylzt.errors import BatchJobFailed, BatchLimitExceeded, MediaNotBatchable, NotFound
from pylzt.models.lot import Lot
from pylzt.storage import BaseStorage, BatchJobRecord
from pylzt.transport.base import Request, Response
from pylzt.types import ApiTarget, HttpMethod, RateClass

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pylzt.methods.base import BaseMethod
    from pylzt.transport.base import BaseTransport
    from pylzt.types import ItemId

MAX_BATCH_JOBS = 10


class BatchJob(BaseModel):
    """One job entry in a POST /batch request — arbitrary method/uri/params, not just
    the lot-id GET shape `_build_batch_request` hardcodes."""

    model_config = ConfigDict(frozen=True)

    id: str
    method: HttpMethod = HttpMethod.GET
    uri: str
    params: Mapping[str, Any] = Field(default_factory=dict)


class BatchJobResult(BaseModel):
    """One job's outcome from a POST /batch response — `item` is the raw (unparsed)
    body a hit returned; the caller applies whatever model's `from_raw` fits the uri
    it asked for, since a mixed batch can span several response shapes."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    ok: bool
    # Any is deliberate: a mixed batch's hits span whatever shape each batched
    # endpoint returns (dict, list, ...) — same polymorphic-body reasoning as
    # `transport.base.Response.body`; the caller's own `parse_response` narrows it.
    item: Any | None = None
    error: str | None = None


def build_generic_batch_request(
    jobs: Sequence[BatchJob], *, rate_class: RateClass = RateClass.GENERAL
) -> Request:
    """Build a single POST /batch request covering at most `MAX_BATCH_JOBS` arbitrary jobs."""
    if len(jobs) > MAX_BATCH_JOBS:
        raise BatchLimitExceeded(count=len(jobs), limit=MAX_BATCH_JOBS)
    body = [
        {"id": job.id, "method": job.method.value, "uri": job.uri, "params": dict(job.params)}
        for job in jobs
    ]
    return Request(method="POST", path="/batch", rate_class=rate_class, json_body=body)


_JOB_MARKER_KEYS = frozenset({"_job_result", "_job_error"})


def parse_generic_batch_body(body: Mapping[str, Any]) -> dict[str, BatchJobResult]:
    """Fan a /batch response body out into one `BatchJobResult` per job id present.

    A hit's entry is `{"_job_result": "ok", **<the batched endpoint's own top-level
    response body>}` — the dispatcher splats the sub-call's real JSON body straight into
    the job dict, it does NOT wrap it under a synthetic `"item"` key of its own (verified
    live: a batched `ListCategories` job comes back as `{"_job_result": "ok", "categories":
    [...]}`, not `{"_job_result": "ok", "item": {"categories": [...]}}`). `GetLot`-shaped
    jobs merely LOOK `"item"`-wrapped because `/{item_id}`'s own single-call response body
    legitimately has `"item"` as its top-level key — `BatchJobResult.item` strips only the
    job markers, so feeding it to a method's own `parse_response` behaves exactly like a
    standalone call.
    """
    jobs = body.get("jobs")
    raw_map: Mapping[str, Any] = jobs if isinstance(jobs, dict) else {}

    results: dict[str, BatchJobResult] = {}
    for job_id, entry in raw_map.items():
        if not isinstance(entry, dict):
            continue
        ok = entry.get("_job_result") == "ok"
        results[job_id] = BatchJobResult(
            job_id=job_id,
            ok=ok,
            item={k: v for k, v in entry.items() if k not in _JOB_MARKER_KEYS} if ok else None,
            error=entry.get("_job_error") if not ok else None,
        )
    return results


def _method_to_job(job_id: str, method: BaseMethod[Any]) -> BatchJob:
    """Turn one `BaseMethod` into its wire `BatchJob` entry — single implementation
    shared by `Client._execute_batch_chunk` and `GenericBatchCollector`, so a query
    vs body-param routing fix only has to happen in one place."""
    request = method.build_request()
    if request.files:
        # The flat /batch job format has no multipart slot — silently dropping `files`
        # here would look like a successful upload to the caller. Fail loud instead
        # (project rule): route a Media-bearing method through plain `execute()`.
        raise MediaNotBatchable(method=type(method).__name__, fields=tuple(request.files))
    return BatchJob(
        id=job_id,
        method=HttpMethod(request.method),
        uri=request.path,
        params=request.query
        if request.method == HttpMethod.GET.value
        else (request.json_body if isinstance(request.json_body, dict) else {}),
    )


def _build_batch_request(item_ids: Sequence[ItemId]) -> Request:
    """Build a single POST /batch request covering at most `MAX_BATCH_JOBS` item_ids."""
    jobs = [
        BatchJob(id=str(int(iid)), method=HttpMethod.GET, uri=f"/{int(iid)}") for iid in item_ids
    ]
    return build_generic_batch_request(jobs)


def _parse_batch_body(
    body: dict[str, Any],
    item_ids: Sequence[ItemId],
) -> dict[ItemId, Lot]:
    """Fan parsed Lots out of a /batch response body (`_job_result` per id)."""
    results = parse_generic_batch_body(body)

    result: dict[ItemId, Lot] = {}
    for item_id in item_ids:
        entry = results.get(str(int(item_id)))
        if entry is None or not entry.ok or not isinstance(entry.item, dict):
            continue
        item = entry.item.get("item")
        if isinstance(item, dict) and "item_id" in item:
            result[item_id] = Lot.from_raw(item)
    return result


class BatchExecutor:
    """Coalesces concurrent item-id reads into /batch request(s) per window.

    Each `submit` call is logically one read; internally submissions are grouped
    and flushed on size or linger:
    - when `batch_size` items are pending → immediate flush (scheduled as a task)
    - when `batch_linger` seconds elapse since the first submission → linger flush

    A flush issues one POST /batch per `MAX_BATCH_JOBS`-sized chunk of the pending
    set (the server rejects more than that in one request), running the chunks
    concurrently — so `batch_size` controls coalescing width, not lease count.
    """

    def __init__(self, transport: BaseTransport, batch_size: int, batch_linger: float) -> None:
        self._transport = transport
        self._batch_size = batch_size
        self._batch_linger = batch_linger
        self._pending: dict[ItemId, asyncio.Future[Lot]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        # Keeps strong references to fire-and-forget flush tasks (prevents premature GC).
        self._tasks: set[asyncio.Task[None]] = set()

    async def submit(self, item_id: ItemId) -> Lot:
        """Register a read for item_id and await the result (coalesced with concurrent calls).

        Raises NotFound if item_id is absent from the batch response.
        """
        loop = asyncio.get_running_loop()
        async with self._lock:
            if item_id not in self._pending:
                fut: asyncio.Future[Lot] = loop.create_future()
                self._pending[item_id] = fut
                if len(self._pending) >= self._batch_size:
                    # Batch full — schedule immediate flush outside the lock.
                    _task = asyncio.create_task(self._do_flush())
                    self._tasks.add(_task)
                    _task.add_done_callback(self._tasks.discard)
                elif self._flush_task is None:
                    # First item in this window — start the linger timer.
                    self._flush_task = asyncio.create_task(self._linger_flush())
            # Always read the future from the dict so re-submits share the same future.
            pending_fut = self._pending[item_id]
        return await pending_fut

    async def _linger_flush(self) -> None:
        await asyncio.sleep(self._batch_linger)
        await self._do_flush()

    async def _do_flush(self) -> None:
        async with self._lock:
            if not self._pending:
                return
            pending = dict(self._pending)
            self._pending.clear()
            # Only cancel a still-pending linger timer, never the task we're running in —
            # an immediate size-triggered flush calls this from a fresh task and must
            # cancel the older linger task, but the linger path calls this on ITSELF
            # (_linger_flush awaits _do_flush in the same task); self-cancel there would
            # inject a CancelledError at our own next await and deadlock every future.
            current = asyncio.current_task()
            if (
                self._flush_task is not None
                and self._flush_task is not current
                and not self._flush_task.done()
            ):
                self._flush_task.cancel()
            self._flush_task = None

        # Send outside the lock so new submissions can queue while chunks are in-flight.
        item_ids = list(pending.keys())
        chunks = [item_ids[i : i + MAX_BATCH_JOBS] for i in range(0, len(item_ids), MAX_BATCH_JOBS)]
        await asyncio.gather(*(self._flush_chunk(chunk, pending) for chunk in chunks))

    async def _flush_chunk(
        self, item_ids: list[ItemId], pending: dict[ItemId, asyncio.Future[Lot]]
    ) -> None:
        try:
            resp = await self._transport.send(_build_batch_request(item_ids))
            lots = _parse_batch_body(resp.body, item_ids)
            for iid in item_ids:
                fut = pending[iid]
                if fut.done():
                    continue
                if iid in lots:
                    fut.set_result(lots[iid])
                else:
                    fut.set_exception(NotFound(iid))
        except Exception as exc:  # fans a chunk failure out to each waiting future
            for iid in item_ids:
                fut = pending[iid]
                if not fut.done():
                    fut.set_exception(exc)


class GenericBatchCollector:
    """`Client.batching()`'s coalescer — same window/chunk shape as `BatchExecutor`,
    but keyed by an arbitrary `BaseMethod` instead of a lot `item_id`, so it can
    batch heterogeneous calls the way `Client.execute_batch` does for an eager list.

    Pending jobs are grouped by `method.__api__` before chunking (`/batch` is
    host-specific — a market call and a forum call issued in the same window end up
    as two separate POST /batch calls, not a `MixedBatchApiTargets` error, since
    `batching()` is opportunistic/implicit unlike `execute_batch`'s explicit list).
    """

    def __init__(
        self,
        transport_for: Callable[[BaseMethod[Any]], BaseTransport],
        batch_size: int,
        batch_linger: float,
        storage: BaseStorage,
    ) -> None:
        self._transport_for = transport_for
        self._batch_size = batch_size
        self._batch_linger = batch_linger
        self._storage = storage
        self._pending: dict[str, tuple[BaseMethod[Any], asyncio.Future[Any]]] = {}
        self._next_id = 0
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    async def submit[T](self, method: BaseMethod[T]) -> T:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[T] = loop.create_future()
        async with self._lock:
            self._next_id += 1
            key = str(self._next_id)
            self._pending[key] = (method, fut)
            if len(self._pending) >= self._batch_size:
                task = asyncio.create_task(self._do_flush())
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            elif self._flush_task is None:
                self._flush_task = asyncio.create_task(self._linger_flush())
        return await fut

    async def _linger_flush(self) -> None:
        await asyncio.sleep(self._batch_linger)
        await self._do_flush()

    async def _do_flush(self) -> None:
        async with self._lock:
            if not self._pending:
                return
            pending = dict(self._pending)
            self._pending.clear()
            current = asyncio.current_task()
            if (
                self._flush_task is not None
                and self._flush_task is not current
                and not self._flush_task.done()
            ):
                self._flush_task.cancel()
            self._flush_task = None

        groups: dict[ApiTarget, list[tuple[BaseMethod[Any], asyncio.Future[Any]]]] = {}
        for method, fut in pending.values():
            groups.setdefault(method.__api__, []).append((method, fut))

        chunks: list[list[tuple[BaseMethod[Any], asyncio.Future[Any]]]] = []
        for group in groups.values():
            chunks.extend(
                group[i : i + MAX_BATCH_JOBS] for i in range(0, len(group), MAX_BATCH_JOBS)
            )
        await asyncio.gather(*(self._flush_group(chunk) for chunk in chunks))

    async def _flush_group(self, jobs: list[tuple[BaseMethod[Any], asyncio.Future[Any]]]) -> None:
        # Job ids are re-keyed 1-indexed per chunk (server-side scoping, matches
        # Client._execute_batch_chunk's own convention — id "0" is a PHP falsy quirk).
        local_ids = {str(i + 1): pair for i, pair in enumerate(jobs)}
        batch_jobs = [_method_to_job(job_id, method) for job_id, (method, _) in local_ids.items()]
        methods = [method for method, _ in local_ids.values()]
        rate_class = RateClass.FORUM if methods[0].__api__ is ApiTarget.FORUM else RateClass.GENERAL

        try:
            transport = self._transport_for(methods[0])
            request = build_generic_batch_request(batch_jobs, rate_class=rate_class)
            response = await transport.send(request)
            results = parse_generic_batch_body(response.body)
        except Exception as exc:
            for _, fut in local_ids.values():
                if not fut.done():
                    fut.set_exception(exc)
            return

        for job_id, (method, fut) in local_ids.items():
            if fut.done():
                continue
            entry = results.get(job_id)
            if entry is None or not entry.ok:
                fut.set_exception(
                    BatchJobFailed(
                        job_id=job_id,
                        method=type(method).__name__,
                        upstream_error=entry.error if entry is not None else None,
                    )
                )
                continue
            item = entry.item if isinstance(entry.item, dict) else {}
            try:
                fut.set_result(method.parse_response(Response(status=200, body=item)))
            except Exception as exc:
                fut.set_exception(exc)

        # Audit-trail persistence — best-effort, same posture as _save_media: a broken
        # storage impl must never leave a caller's future pending. Results are already
        # resolved above, so this can only fail to record history, not fail the batch.
        with contextlib.suppress(Exception):
            await self._storage.save_jobs(
                [
                    BatchJobRecord(record_id=uuid.uuid4().hex, job=job, result=results.get(job.id))
                    for job in batch_jobs
                ]
            )


# `BatchJobRecord` (storage/batch.py) declares `job: BatchJob` / `result: BatchJobResult | None`
# as forward refs to break the storage<->lib.batch import cycle (storage/batch.py only sees
# these types under TYPE_CHECKING). Pydantic needs the real classes to build that model's
# validator — supply them explicitly now that both are defined, rather than a runtime import
# in storage/batch.py that would deadlock on partially-initialized modules.
BatchJobRecord.model_rebuild(
    _types_namespace={"BatchJob": BatchJob, "BatchJobResult": BatchJobResult}
)

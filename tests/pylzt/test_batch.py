"""Tests for BatchExecutor request-coalescing and _build_batch_request helper.

Wire shapes here match the real /batch protocol, verified live 2026-07-03:
flat job array in, `{"jobs": {"<id>": {"_job_result": ...}}}` out, 10-job cap.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pylzt.config import ClientConfig
from pylzt.errors import BatchJobFailed, BatchLimitExceeded, NotFound
from pylzt.lib.batch import (
    MAX_BATCH_JOBS,
    BatchExecutor,
    GenericBatchCollector,
    _build_batch_request,
)
from pylzt.lib.clock import FakeClock
from pylzt.methods.base import BaseMethod
from pylzt.models.lot import Lot
from pylzt.storage import MemoryStorage
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import ApiTarget, ItemId, RateClass, TokenId


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


class FakeTransport(BaseTransport):
    def __init__(self, response: Response, config: ClientConfig | None = None) -> None:
        super().__init__(token_pool=_pool())
        self.config = config or ClientConfig()
        self._response = response
        self.calls: list[Request] = []

    async def _send_raw(self, req: Request) -> Response:
        self.calls.append(req)
        return self._response


def _raw_lot(item_id: int) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "category": "steam",
        "price": 100,
        "price_currency": "rub",
        "title": f"Lot {item_id}",
        "item_state": "active",
        "item_origin": "resale",
        "guarantee": "24h",
        "nsb": False,
        "published_date": 1700000000,
        "seller": {"user_id": 42},
    }


def _batch_response(item_ids: list[int]) -> Response:
    body: dict[str, Any] = {
        "jobs": {str(iid): {"_job_result": "ok", "item": _raw_lot(iid)} for iid in item_ids}
    }
    return Response(status=200, body=body)


async def test_five_concurrent_submits_produce_one_send_call() -> None:
    ids = list(range(1, 6))
    transport = FakeTransport(_batch_response(ids))
    executor = BatchExecutor(transport, batch_size=50, batch_linger=0.05)

    lots = await asyncio.gather(*[executor.submit(ItemId(i)) for i in ids])

    assert len(transport.calls) == 1, "Expected a single /batch send() call"
    assert all(isinstance(lot, Lot) for lot in lots)
    assert [int(lot.item_id) for lot in lots] == ids


async def test_each_caller_gets_own_lot() -> None:
    transport = FakeTransport(_batch_response([10, 20]))
    executor = BatchExecutor(transport, batch_size=50, batch_linger=0.05)

    lot10, lot20 = await asyncio.gather(
        executor.submit(ItemId(10)),
        executor.submit(ItemId(20)),
    )

    assert int(lot10.item_id) == 10
    assert int(lot20.item_id) == 20


async def test_missing_id_raises_not_found() -> None:
    transport = FakeTransport(_batch_response([1]))
    executor = BatchExecutor(transport, batch_size=50, batch_linger=0.05)

    results = await asyncio.gather(
        executor.submit(ItemId(1)),
        executor.submit(ItemId(2)),
        return_exceptions=True,
    )

    assert isinstance(results[0], Lot)
    assert isinstance(results[1], NotFound)


async def test_error_job_result_raises_not_found() -> None:
    body = {"jobs": {"1": {"_job_result": "error", "_job_error": "not found"}}}
    transport = FakeTransport(Response(status=200, body=body))
    executor = BatchExecutor(transport, batch_size=50, batch_linger=0.05)

    with pytest.raises(NotFound):
        await executor.submit(ItemId(1))


async def test_linger_window_flushes_partial_batch() -> None:
    transport = FakeTransport(_batch_response([7]))
    executor = BatchExecutor(transport, batch_size=50, batch_linger=0.01)

    lot = await executor.submit(ItemId(7))

    assert len(transport.calls) == 1
    assert int(lot.item_id) == 7


async def test_flush_past_server_cap_splits_into_chunk_requests() -> None:
    ids = list(range(1, MAX_BATCH_JOBS + 6))  # one full chunk + a partial second chunk
    transport = FakeTransport(_batch_response(ids))
    executor = BatchExecutor(transport, batch_size=len(ids), batch_linger=0.05)

    lots = await asyncio.gather(*[executor.submit(ItemId(i)) for i in ids])

    assert len(transport.calls) == 2, "Expected two chunked /batch send() calls"
    for req in transport.calls:
        assert isinstance(req.json_body, list)
        assert len(req.json_body) <= MAX_BATCH_JOBS
    assert [int(lot.item_id) for lot in lots] == ids


def test_build_batch_request_shape() -> None:
    req = _build_batch_request([ItemId(1), ItemId(2)])

    assert req.method == "POST"
    assert req.path == "/batch"
    assert req.json_body == [
        {"id": "1", "method": "GET", "uri": "/1", "params": {}},
        {"id": "2", "method": "GET", "uri": "/2", "params": {}},
    ]


def test_build_batch_request_rejects_over_server_cap() -> None:
    with pytest.raises(BatchLimitExceeded):
        _build_batch_request([ItemId(i) for i in range(MAX_BATCH_JOBS + 1)])


class _EchoMarket(BaseMethod[str]):
    __api__ = ApiTarget.MARKET
    path: str

    def build_request(self) -> Request:
        return Request(method="GET", path=self.path, rate_class=RateClass.GENERAL)

    def parse_response(self, response: Response) -> str:
        return str(response.body.get("echo"))


class _EchoForum(BaseMethod[str]):
    __api__ = ApiTarget.FORUM
    path: str

    def build_request(self) -> Request:
        return Request(method="GET", path=self.path, rate_class=RateClass.FORUM)

    def parse_response(self, response: Response) -> str:
        return str(response.body.get("echo"))


class _RecordingTransport(BaseTransport):
    def __init__(self) -> None:
        super().__init__(token_pool=_pool())
        self.calls: list[Request] = []

    async def _send_raw(self, req: Request) -> Response:
        self.calls.append(req)
        assert isinstance(req.json_body, list)
        body = {
            "jobs": {job["id"]: {"_job_result": "ok", "echo": job["uri"]} for job in req.json_body}
        }
        return Response(status=200, body=body)


def _collector(transport: BaseTransport, *, batch_size: int = 50) -> GenericBatchCollector:
    return GenericBatchCollector(
        lambda _method: transport, batch_size, batch_linger=0.05, storage=MemoryStorage()
    )


async def test_generic_collector_five_concurrent_submits_produce_one_send_call() -> None:
    transport = _RecordingTransport()
    collector = _collector(transport)

    results = await asyncio.gather(*[collector.submit(_EchoMarket(path=f"/{i}")) for i in range(5)])

    assert len(transport.calls) == 1
    assert results == [f"/{i}" for i in range(5)]


async def test_generic_collector_each_caller_gets_own_result() -> None:
    transport = _RecordingTransport()
    collector = _collector(transport)

    r1, r2 = await asyncio.gather(
        collector.submit(_EchoMarket(path="/a")), collector.submit(_EchoMarket(path="/b"))
    )

    assert r1 == "/a"
    assert r2 == "/b"


async def test_generic_collector_linger_window_flushes_partial_batch() -> None:
    transport = _RecordingTransport()
    collector = GenericBatchCollector(
        lambda _m: transport, batch_size=50, batch_linger=0.01, storage=MemoryStorage()
    )

    result = await collector.submit(_EchoMarket(path="/solo"))

    assert len(transport.calls) == 1
    assert result == "/solo"


async def test_generic_collector_mixed_api_splits_into_separate_flush_groups() -> None:
    transport = _RecordingTransport()
    collector = _collector(transport)

    market_result, forum_result = await asyncio.gather(
        collector.submit(_EchoMarket(path="/m")), collector.submit(_EchoForum(path="/f"))
    )

    assert market_result == "/m"
    assert forum_result == "/f"
    assert len(transport.calls) == 2  # market and forum never share one /batch call


async def test_generic_collector_server_side_job_error_surfaces_batch_job_failed() -> None:
    class _FailingTransport(BaseTransport):
        def __init__(self) -> None:
            super().__init__(token_pool=_pool())

        async def _send_raw(self, req: Request) -> Response:
            return Response(
                status=200, body={"jobs": {"1": {"_job_result": "error", "_job_error": "nope"}}}
            )

    collector = _collector(_FailingTransport())

    with pytest.raises(BatchJobFailed):
        await collector.submit(_EchoMarket(path="/x"))


async def test_generic_collector_storage_failure_does_not_leak_pending_futures() -> None:
    """A broken save_jobs must never leave an already-resolved result stuck —
    it's a best-effort audit trail, not a gate on delivering the batch result."""

    class _BrokenStorage(MemoryStorage):
        async def save_jobs(self, records: object) -> None:
            raise RuntimeError("storage backend is down")

    transport = _RecordingTransport()
    collector = GenericBatchCollector(
        lambda _method: transport, batch_size=50, batch_linger=0.05, storage=_BrokenStorage()
    )

    result = await asyncio.wait_for(collector.submit(_EchoMarket(path="/ok")), timeout=1.0)

    assert result == "/ok"


async def test_generic_collector_over_cap_splits_into_chunk_requests() -> None:
    transport = _RecordingTransport()
    collector = _collector(transport, batch_size=MAX_BATCH_JOBS + 5)

    methods = [_EchoMarket(path=f"/{i}") for i in range(MAX_BATCH_JOBS + 5)]
    results = await asyncio.gather(*[collector.submit(m) for m in methods])

    assert len(transport.calls) == 2
    assert results == [m.path for m in methods]

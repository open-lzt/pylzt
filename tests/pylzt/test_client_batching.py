"""`Client.batching()` — implicit request-coalescing context manager."""

from __future__ import annotations

import asyncio

from pylzt.client import Client
from pylzt.lib.clock import FakeClock
from pylzt.methods.base import BaseMethod
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import ApiTarget, RateClass, TokenId


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


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
        if req.path == "/batch":
            assert isinstance(req.json_body, list)
            body = {
                "jobs": {
                    job["id"]: {"_job_result": "ok", "echo": job["uri"]} for job in req.json_body
                }
            }
            return Response(status=200, body=body)
        return Response(status=200, body={"echo": req.path})


async def test_batching_coalesces_five_concurrent_executes_into_one_batch_call() -> None:
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        async with client.batching():
            results = await asyncio.gather(
                *[client.execute(_EchoMarket(path=f"/{i}")) for i in range(5)]
            )

    batch_calls = [c for c in transport.calls if c.path == "/batch"]
    assert len(batch_calls) == 1
    assert results == [f"/{i}" for i in range(5)]


async def test_batching_exit_force_flushes_stragglers() -> None:
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        async with client.batching(batch_size=50, batch_linger=10.0):
            result = await client.execute(_EchoMarket(path="/solo"))

    batch_calls = [c for c in transport.calls if c.path == "/batch"]
    assert len(batch_calls) == 1  # exit flushed it, not the 10s linger timer
    assert result == "/solo"


async def test_batching_mixed_api_produces_two_batch_calls() -> None:
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport, forum_transport=transport) as client:
        async with client.batching():
            market_result, forum_result = await asyncio.gather(
                client.execute(_EchoMarket(path="/m")), client.execute(_EchoForum(path="/f"))
            )

    batch_calls = [c for c in transport.calls if c.path == "/batch"]
    assert len(batch_calls) == 2
    assert market_result == "/m"
    assert forum_result == "/f"


async def test_outside_batching_block_executes_are_not_batched() -> None:
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        result = await client.execute(_EchoMarket(path="/direct"))

    batch_calls = [c for c in transport.calls if c.path == "/batch"]
    assert batch_calls == []  # never went through /batch
    assert result == "/direct"


async def test_execute_batch_eager_api_still_works_unchanged() -> None:
    """Client.execute_batch()'s existing eager-list path is untouched by batching()."""
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        results = await client.execute_batch([_EchoMarket(path="/1"), _EchoMarket(path="/2")])

    batch_calls = [c for c in transport.calls if c.path == "/batch"]
    assert len(batch_calls) == 1
    assert results == ["/1", "/2"]


async def test_job_coalesces_concurrent_calls_without_a_batching_block() -> None:
    """`job()` batches with other `job()` calls even with no `async with client.batching():`."""
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        results = await asyncio.gather(*[client.job(_EchoMarket(path=f"/{i}")) for i in range(5)])

    batch_calls = [c for c in transport.calls if c.path == "/batch"]
    assert len(batch_calls) == 1
    assert results == [f"/{i}" for i in range(5)]


async def test_job_inside_batching_block_shares_that_scopes_collector() -> None:
    """`job()` called inside an active `batching()` block behaves like `execute()` there —
    one shared collector, not two separate batch windows."""
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        async with client.batching():
            results = await asyncio.gather(
                client.execute(_EchoMarket(path="/a")), client.job(_EchoMarket(path="/b"))
            )

    batch_calls = [c for c in transport.calls if c.path == "/batch"]
    assert len(batch_calls) == 1
    assert results == ["/a", "/b"]


async def test_job_outside_any_block_is_not_a_direct_call() -> None:
    """A standalone `job()` call (no batching() block, no concurrent siblings) still
    routes through /batch — unlike execute(), which would call the endpoint directly."""
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        result = await client.job(_EchoMarket(path="/solo"))

    batch_calls = [c for c in transport.calls if c.path == "/batch"]
    assert len(batch_calls) == 1
    assert result == "/solo"

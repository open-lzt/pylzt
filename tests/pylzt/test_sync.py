"""SyncRunner + SyncClient — sync-over-async substrate and facade."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from pylzt.lib.clock import FakeClock
from pylzt.sync.client import SyncClient
from pylzt.sync.runner import SyncRunner
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import TokenId


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


async def _double(x: int) -> int:
    await asyncio.sleep(0.01)
    return x * 2


def test_sync_runner_blocks_and_returns_result() -> None:
    runner = SyncRunner()
    assert runner.run(_double(5)) == 10
    runner.close()


def test_sync_runner_close_is_idempotent() -> None:
    runner = SyncRunner()
    runner.run(_double(1))
    runner.close()
    runner.close()  # must not raise


def test_sync_runner_lazy_start_no_thread_until_first_run() -> None:
    runner = SyncRunner()
    assert runner._loop is None
    assert runner._thread is None
    runner.run(_double(1))
    assert runner._loop is not None
    assert runner._thread is not None
    runner.close()


async def test_sync_runner_callable_from_inside_a_running_loop() -> None:
    """`.run()` must work even when the calling thread already has its own
    running event loop (unlike `asyncio.run()`, which raises `RuntimeError`
    there) — proven by calling it from a thread spawned inside this async test."""
    runner = SyncRunner()
    with ThreadPoolExecutor(1) as ex:
        result = await asyncio.get_event_loop().run_in_executor(ex, runner.run, _double(21))
    assert result == 42
    runner.close()


def test_sync_runner_concurrent_run_calls() -> None:
    runner = SyncRunner()
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda i: runner.run(_double(i)), range(8)))
    assert results == [i * 2 for i in range(8)]
    runner.close()


class _FakeTransport(BaseTransport):
    def __init__(self) -> None:
        super().__init__(token_pool=_pool())
        self.sent: list[Request] = []

    async def _send_raw(self, req: Request) -> Response:
        self.sent.append(req)
        return Response(status=200, body={"message": {"ok": True}})

    async def aclose(self) -> None:
        return None


def test_sync_client_constructs_synchronously() -> None:
    with SyncClient(tokens=["tok"], transport=_FakeTransport()) as client:
        assert client.market is not None
        assert client.forum is not None
        assert client.antipublic is not None


def test_sync_client_market_method_returns_blocking() -> None:
    transport = _FakeTransport()
    with SyncClient(tokens=["tok"], transport=transport) as client:
        result = client.market.managing_check_guarantee(item_id=1)
    assert result == {"ok": True}  # __unwrap__ = "message" dug out before passthrough
    assert transport.sent[0].method == "POST"


def test_sync_client_is_a_context_manager() -> None:
    client = SyncClient(tokens=["tok"], transport=_FakeTransport())
    with client as ctx:
        assert ctx is client


def test_sync_client_double_close_is_safe() -> None:
    client = SyncClient(tokens=["tok"], transport=_FakeTransport())
    client.close()
    client.close()  # must not raise or re-spin the runner thread

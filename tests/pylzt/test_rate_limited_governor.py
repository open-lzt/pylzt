"""`BaseTransport.send()` <-> `BaseConcurrencyGovernor` wiring."""

from __future__ import annotations

from typing import Any

from pylzt.client import Client
from pylzt.config import ClientConfig
from pylzt.lib.clock import FakeClock
from pylzt.token_pool.base import BaseTokenPool, Token
from pylzt.token_pool.governor import (
    AimdConcurrencyGovernor,
    BaseConcurrencyGovernor,
    NullConcurrencyGovernor,
)
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import RateClass, TokenId


class _RecordingGate:
    def __init__(self) -> None:
        self.acquired = False

    def acquire(self) -> _RecordingCM:
        return _RecordingCM(self)


class _RecordingCM:
    def __init__(self, gate: _RecordingGate) -> None:
        self._gate = gate

    async def __aenter__(self) -> None:
        self._gate.acquired = True

    async def __aexit__(self, *exc: object) -> None:
        return None


class _SpyGovernor:
    def __init__(self) -> None:
        self.gate_obj = _RecordingGate()
        self.observed: list[tuple[RateClass, Any]] = []

    def gate(self, rate_class: RateClass) -> _RecordingGate:
        return self.gate_obj

    def observe(self, rate_class: RateClass, snapshot: Any) -> None:
        self.observed.append((rate_class, snapshot))


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


class _MemoryTransport(BaseTransport):
    def __init__(
        self,
        body: dict[str, object],
        *,
        token_pool: BaseTokenPool | None = None,
        concurrency_governor: BaseConcurrencyGovernor | None = None,
    ) -> None:
        super().__init__(
            token_pool=token_pool or _pool(), concurrency_governor=concurrency_governor
        )
        self._body = body

    async def _send_raw(self, req: Request) -> Response:
        return Response(status=200, body=self._body)


def _snapshot_body(remaining: int) -> dict[str, object]:
    return {"system_info": {"rate_limit": {"limit": 100, "remaining": remaining, "reset": 0}}}


async def test_gate_acquired_before_token_lease() -> None:
    spy = _SpyGovernor()
    transport = _MemoryTransport(
        _snapshot_body(90),
        concurrency_governor=spy,  # type: ignore[arg-type]
    )

    await transport.send(Request(method="GET", path="/", rate_class=RateClass.GENERAL))

    assert spy.gate_obj.acquired is True


async def test_observe_called_once_per_successful_response() -> None:
    spy = _SpyGovernor()
    transport = _MemoryTransport(
        _snapshot_body(90),
        concurrency_governor=spy,  # type: ignore[arg-type]
    )

    await transport.send(Request(method="GET", path="/", rate_class=RateClass.GENERAL))

    assert len(spy.observed) == 1
    assert spy.observed[0][0] is RateClass.GENERAL


async def test_default_null_governor_never_resizes_across_varying_snapshots() -> None:
    baseline = _MemoryTransport({})
    gate_before = baseline._concurrency_governor.gate(RateClass.GENERAL).limit

    for remaining in (5, 50, 1):
        transport = _MemoryTransport(_snapshot_body(remaining))
        await transport.send(Request(method="GET", path="/", rate_class=RateClass.GENERAL))
        assert transport._concurrency_governor.gate(RateClass.GENERAL).limit == gate_before


async def test_client_enable_adaptive_concurrency_wires_aimd_governor() -> None:
    client = Client(
        tokens=["tok"],
        transport=_MemoryTransport({}),
        config=ClientConfig(enable_adaptive_concurrency=True),
    )
    assert isinstance(client._concurrency_governor, AimdConcurrencyGovernor)


async def test_client_default_wires_null_governor() -> None:
    client = Client(tokens=["tok"], transport=_MemoryTransport({}))
    assert isinstance(client._concurrency_governor, NullConcurrencyGovernor)

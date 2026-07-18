"""`Client` wiring for entry-point plugin discovery — precedence + opt-out."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, PrivateAttr

from pylzt.client import Client
from pylzt.config import ClientConfig
from pylzt.lib.clock import FakeClock
from pylzt.lib.metrics import BaseMetrics
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.transport.middleware import BaseMiddleware, Next
from pylzt.types import TokenId


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


class _MemoryTransport(BaseTransport):
    def __init__(self) -> None:
        super().__init__(token_pool=_pool())
        self.sent: list[Request] = []

    async def _send_raw(self, req: Request) -> Response:
        self.sent.append(req)
        return Response(status=200, body={"ok": True})


class _ExplicitMetrics(BaseMetrics):
    def incr(self, name: str, value: int = 1, **labels: str) -> None:
        return None

    def gauge(self, name: str, value: float, **labels: str) -> None:
        return None

    def observe(self, name: str, value: float, **labels: str) -> None:
        return None


class _DiscoveredMetrics(_ExplicitMetrics):
    pass


class _DiscoveredMiddleware(BaseMiddleware):
    async def __call__(self, request: Request, call_next: Next) -> Response:
        return await call_next(request)


class _FakeEntryPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    _target: type[Any] = PrivateAttr()

    def __init__(self, name: str, target: type[Any]) -> None:
        super().__init__(name=name)
        self._target = target

    def load(self) -> type[Any]:
        return self._target


def test_explicit_metrics_wins_over_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pylzt.plugins.entry_points",
        lambda group: (
            [_FakeEntryPoint("m", _DiscoveredMetrics)]
            if group == "pylzt.plugins.metrics"
            else []
        ),
    )
    explicit = _ExplicitMetrics()
    client = Client(tokens=["tok"], transport=_MemoryTransport(), metrics=explicit)

    assert client._metrics is explicit


def test_discovery_disabled_never_calls_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(group: str) -> Any:
        raise AssertionError("entry_points() must not be called when discovery is disabled")

    monkeypatch.setattr("pylzt.plugins.entry_points", _boom)
    client = Client(
        tokens=["tok"],
        transport=_MemoryTransport(),
        config=ClientConfig(enable_plugin_discovery=False),
    )

    assert client._plugin_middlewares == ()


def test_discovered_middlewares_registered_on_raw_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pylzt.plugins.entry_points",
        lambda group: (
            [_FakeEntryPoint("mw", _DiscoveredMiddleware)]
            if group == "pylzt.plugins.middleware"
            else []
        ),
    )
    client = Client(tokens=["tok"])  # no explicit transport -> exercises _raw_transport

    raw = client._transport
    assert any(
        isinstance(m, _DiscoveredMiddleware)
        for m in raw.request_middlewares.middlewares  # type: ignore[attr-defined]
    )

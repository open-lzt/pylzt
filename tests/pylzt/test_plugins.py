"""Entry-point plugin discovery — `pylzt.plugins.middleware` / `.metrics`."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, PrivateAttr

from pylzt.errors import AmbiguousPlugin
from pylzt.lib.metrics import BaseMetrics
from pylzt.plugins import METRICS_GROUP, MIDDLEWARE_GROUP, discover_metrics, discover_middlewares
from pylzt.transport.base import Request, Response
from pylzt.transport.middleware import BaseMiddleware, Next


class _FakeMiddleware(BaseMiddleware):
    async def __call__(self, request: Request, call_next: Next) -> Response:
        return await call_next(request)


class _FakeMiddlewareB(BaseMiddleware):
    async def __call__(self, request: Request, call_next: Next) -> Response:
        return await call_next(request)


class _FakeMetrics(BaseMetrics):
    def incr(self, name: str, value: int = 1, **labels: str) -> None:
        return None

    def gauge(self, name: str, value: float, **labels: str) -> None:
        return None

    def observe(self, name: str, value: float, **labels: str) -> None:
        return None


class _FakeMetricsB(_FakeMetrics):
    pass


class _FakeEntryPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    _target: type[Any] = PrivateAttr()

    def __init__(self, name: str, target: type[Any]) -> None:
        super().__init__(name=name)
        self._target = target

    def load(self) -> type[Any]:
        return self._target


def test_discover_middlewares_zero_registrations_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pylzt.plugins.entry_points", lambda group: [])
    assert discover_middlewares() == ()


def test_discover_middlewares_one_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    eps = [_FakeEntryPoint("mw1", _FakeMiddleware)]
    monkeypatch.setattr(
        "pylzt.plugins.entry_points",
        lambda group: eps if group == MIDDLEWARE_GROUP else [],
    )
    result = discover_middlewares()
    assert len(result) == 1
    assert isinstance(result[0], _FakeMiddleware)


def test_discover_middlewares_two_registrations_both_constructed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eps = [_FakeEntryPoint("mw1", _FakeMiddleware), _FakeEntryPoint("mw2", _FakeMiddlewareB)]
    monkeypatch.setattr(
        "pylzt.plugins.entry_points",
        lambda group: eps if group == MIDDLEWARE_GROUP else [],
    )
    result = discover_middlewares()
    assert len(result) == 2  # additive, no error on multiple


def test_discover_metrics_zero_registrations_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pylzt.plugins.entry_points", lambda group: [])
    assert discover_metrics() is None


def test_discover_metrics_one_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    eps = [_FakeEntryPoint("m1", _FakeMetrics)]
    monkeypatch.setattr(
        "pylzt.plugins.entry_points", lambda group: eps if group == METRICS_GROUP else []
    )
    result = discover_metrics()
    assert isinstance(result, _FakeMetrics)


def test_discover_metrics_two_registrations_raises_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eps = [_FakeEntryPoint("m1", _FakeMetrics), _FakeEntryPoint("m2", _FakeMetricsB)]
    monkeypatch.setattr(
        "pylzt.plugins.entry_points", lambda group: eps if group == METRICS_GROUP else []
    )
    with pytest.raises(AmbiguousPlugin) as exc_info:
        discover_metrics()
    assert exc_info.value.group == METRICS_GROUP
    assert set(exc_info.value.names) == {"m1", "m2"}

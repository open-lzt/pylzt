"""HttpxSession — middleware chain ordering and status → typed-error mapping."""

from __future__ import annotations

import httpx
import pytest

from pylzt.errors import NotFound
from pylzt.lib.clock import FakeClock
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import Request, Response
from pylzt.transport.middleware import BaseMiddleware, Next, stable_id
from pylzt.transport.session import HttpxSession
from pylzt.types import RateClass, TokenId


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


def _req(path: str) -> Request:
    return Request(method="GET", path=path, rate_class=RateClass.GENERAL)


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, base_url="http://test")


class _Recorder(BaseMiddleware):
    def __init__(self, tag: str, log: list[str]) -> None:
        self._tag = tag
        self._log = log

    async def __call__(self, request: Request, call_next: Next) -> Response:
        self._log.append(f"{self._tag}:before")
        response = await call_next(request)
        self._log.append(f"{self._tag}:after")
        return response


# Distinct classes: the manager dedups by class (aiogram convention), so two
# instances of one middleware class would collide — ordering needs two types.
class _RecA(_Recorder): ...


class _RecB(_Recorder): ...


async def test_middleware_chain_runs_as_an_onion() -> None:
    order: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    session = HttpxSession(
        middlewares=[_RecA("a", order), _RecB("b", order)],
        client=_client(httpx.MockTransport(handle)),
        token_pool=_pool(),
    )
    resp = await session.send(_req("/x"))
    await session.aclose()

    assert resp.status == 200
    assert order == ["a:before", "b:before", "b:after", "a:after"]


async def test_session_maps_status_to_typed_error() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    session = HttpxSession(client=_client(httpx.MockTransport(handle)), token_pool=_pool())
    with pytest.raises(NotFound):
        await session.send(_req("/missing"))
    await session.aclose()


async def test_middlewares_register_via_decorator_and_unregister() -> None:
    order: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    session = HttpxSession(client=_client(httpx.MockTransport(handle)), token_pool=_pool())

    @session.request_middlewares
    class First(BaseMiddleware):
        async def __call__(self, request: Request, call_next: Next) -> Response:
            order.append("first")
            return await call_next(request)

    session.request_middlewares.register(_Recorder("rec", order))

    await session.send(_req("/x"))
    assert order == ["first", "rec:before", "rec:after"]  # decorated = outermost

    order.clear()
    assert session.request_middlewares.unregister(stable_id(First))
    await session.send(_req("/x"))
    assert order == ["rec:before", "rec:after"]  # First removed
    await session.aclose()

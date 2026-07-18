"""`Client.reconfigure` — hot-swap the live token pool, no restart (library-design Law 28)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pylzt.client import Client
from pylzt.token_pool.base import BaseTokenPool, Lease, Token
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import RateClass, TokenId


class _FakeTokenPool(BaseTokenPool):
    def __init__(self, token_id: str) -> None:
        self._token = Token(token_id=TokenId(token_id), credential=token_id)

    @asynccontextmanager
    async def lease(self, rate_class: RateClass) -> AsyncIterator[Lease]:
        yield Lease(token=self._token, proxy=None)


class _FakeTransport(BaseTransport):
    def __init__(self, token_pool: BaseTokenPool | None = None) -> None:
        super().__init__(token_pool=token_pool or _FakeTokenPool("initial"))

    async def _send_raw(self, req: Request) -> Response:
        return Response(status=200, body={"ok": True})


def _client() -> Client:
    return Client(
        tokens=["secret-cred"], transport=_FakeTransport(), forum_transport=_FakeTransport()
    )


async def test_reconfigure_swaps_token_pool_on_both_transports() -> None:
    client = _client()
    old_pool = client._token_pool
    new_pool = _FakeTokenPool("rotated")

    client.reconfigure(token_pool=new_pool)

    assert client._token_pool is new_pool
    assert client._token_pool is not old_pool
    assert client._transport._token_pool is new_pool
    assert client._forum_transport._token_pool is new_pool


async def test_reconfigure_with_no_args_is_a_noop() -> None:
    client = _client()
    old_pool = client._token_pool

    client.reconfigure()

    assert client._token_pool is old_pool


async def test_new_pool_actually_signs_subsequent_requests() -> None:
    client = _client()
    client.reconfigure(token_pool=_FakeTokenPool("rotated"))

    resp = await client._transport.send(
        Request(method="GET", path="/", rate_class=RateClass.GENERAL)
    )

    assert resp.body == {"ok": True}

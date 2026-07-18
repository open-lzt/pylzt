"""Shared contract for `BaseTransport` — send returns OUR `Response`, aclose is idempotent.

`HttpxSession` is the SDK's only transport, driven offline by an `httpx.MockTransport` —
a future own-reverse backend slots straight into this contract. The point Law 21 makes:
one set of assertions pins the seam's semantics so backends can't diverge.
"""

from __future__ import annotations

import httpx

from pylzt.lib.clock import FakeClock
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, ProxySpec, Request, Response
from pylzt.transport.session import HttpxSession
from pylzt.types import ProxyScheme, RateClass, TokenId


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


class BaseTransportContract:
    def make_transport(self) -> BaseTransport:
        raise NotImplementedError

    async def test_send_returns_our_response_dto(self) -> None:
        transport = self.make_transport()
        resp = await transport.send(Request(method="GET", path="/ok", rate_class=RateClass.GENERAL))
        assert isinstance(resp, Response)  # our DTO, never an httpx.Response (Law 18)
        assert resp.status == 200
        await transport.aclose()

    async def test_aclose_is_idempotent(self) -> None:
        transport = self.make_transport()
        await transport.aclose()
        await transport.aclose()  # second call must not raise


class TestHttpxSession(BaseTransportContract):
    def make_transport(self) -> BaseTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="http://test")
        return HttpxSession(client=client, token_pool=_pool())


async def test_distinct_proxies_get_distinct_pooled_clients() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    session = HttpxSession(base_url="http://test", token_pool=_pool())
    proxy_a = ProxySpec(scheme=ProxyScheme.HTTP, host="a.example", port=8080)
    proxy_b = ProxySpec(scheme=ProxyScheme.HTTP, host="b.example", port=8080)

    client_a1 = session._client_for(proxy_a)
    client_a2 = session._client_for(proxy_a)
    client_b = session._client_for(proxy_b)
    client_direct = session._client_for(None)

    assert client_a1 is client_a2  # same proxy reuses the pooled client
    assert client_a1 is not client_b
    assert client_a1 is not client_direct
    await session.aclose()


async def test_aclose_closes_every_pooled_client() -> None:
    session = HttpxSession(base_url="http://test", token_pool=_pool())
    proxy = ProxySpec(scheme=ProxyScheme.HTTP, host="a.example", port=8080)
    direct = session._client_for(None)
    proxied = session._client_for(proxy)

    await session.aclose()

    assert direct.is_closed
    assert proxied.is_closed
    assert session._clients == {}


async def test_non_json_body_lands_in_response_text() -> None:
    """`ListDownload`/`ManagingSteamPreview`/`PublicCountLinesPlain` declare a
    `text/html`/`text/plain` 200 with a bare string schema, not JSON — `body` stays
    `{}` (there's no dict to decode) but `text` must carry the real payload."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"<html>steam preview</html>", headers={"content-type": "text/html"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="http://test")
    session = HttpxSession(client=client, token_pool=_pool())
    resp = await session.send(Request(method="GET", path="/x", rate_class=RateClass.GENERAL))

    assert resp.body == {}
    assert resp.text == "<html>steam preview</html>"
    await session.aclose()


async def test_direct_request_reuses_injected_client() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url="http://test")
    session = HttpxSession(client=injected, token_pool=_pool())

    assert session._client_for(None) is injected
    await session.send(Request(method="GET", path="/x", rate_class=RateClass.GENERAL))
    assert session._client_for(None) is injected  # no second client built for direct traffic
    await session.aclose()

"""Client.request — the rate-limited escape hatch to arbitrary endpoints."""

from __future__ import annotations

from pylzt.client import Client
from pylzt.lib.clock import FakeClock
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import TokenId


class _RecordingTransport(BaseTransport):
    def __init__(self) -> None:
        pool = RoundRobinTokenPool(
            [Token(token_id=TokenId("tok0"), credential="tok")], clock=FakeClock()
        )
        super().__init__(token_pool=pool)
        self.sent: list[Request] = []

    async def _send_raw(self, req: Request) -> Response:
        self.sent.append(req)
        return Response(status=200, body={"ok": True})

    async def aclose(self) -> None:
        return None


async def test_request_runs_through_the_rate_limited_rail() -> None:
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        resp = await client.request("GET", "/custom/endpoint", query={"x": "1"})

    assert resp.status == 200
    assert resp.body == {"ok": True}

    sent = transport.sent[0]
    assert sent.method == "GET"
    assert sent.path == "/custom/endpoint"
    assert sent.query == {"x": "1"}
    assert sent.bearer == "tok"  # signed by the token pool, not passed by the caller

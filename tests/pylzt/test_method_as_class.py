"""BaseMethod — a consumer-defined operation executed through the client rail."""

from __future__ import annotations

from pylzt.client import Client
from pylzt.lib.clock import FakeClock
from pylzt.methods.base import BaseMethod, passthrough
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import RateClass, TokenId


class _Echo(BaseMethod[str]):
    path: str

    def build_request(self) -> Request:
        return Request(method="GET", path=self.path, rate_class=RateClass.GENERAL)

    def parse_response(self, response: Response) -> str:
        return str(response.body.get("echo"))


class _StubTransport(BaseTransport):
    def __init__(self) -> None:
        pool = RoundRobinTokenPool(
            [Token(token_id=TokenId("tok0"), credential="tok")], clock=FakeClock()
        )
        super().__init__(token_pool=pool)
        self.sent: list[Request] = []

    async def _send_raw(self, req: Request) -> Response:
        self.sent.append(req)
        return Response(status=200, body={"echo": req.path})

    async def aclose(self) -> None:
        return None


async def test_method_as_class_executes_via_rail() -> None:
    transport = _StubTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        result = await client.execute(_Echo(path="/hello"))

    assert result == "/hello"
    assert transport.sent[0].path == "/hello"
    assert transport.sent[0].bearer == "tok"  # ran through the token-pool rail


class _RawText(BaseMethod[str]):
    """Mirrors ListDownload/ManagingSteamPreview/PublicCountLinesPlain: a 200 whose
    schema is a bare string, not JSON — `body` stays `{}`, `text` carries the payload."""

    __url__ = "/raw"
    __returning__ = passthrough


async def test_passthrough_prefers_response_text_over_empty_body() -> None:
    class _RawTextTransport(_StubTransport):
        async def _send_raw(self, req: Request) -> Response:
            return Response(status=200, body={}, text="<html>preview</html>")

    async with Client(tokens=["tok"], transport=_RawTextTransport()) as client:
        result = await client.execute(_RawText())

    assert result == "<html>preview</html>"

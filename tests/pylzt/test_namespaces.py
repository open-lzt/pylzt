"""client.market/.forum/.antipublic namespace wiring, antipublic transport routing,
and ClientConfig antipublic defaults."""

from __future__ import annotations

import pytest

from pylzt.client import Client
from pylzt.config import ClientConfig
from pylzt.errors import CredentialMissing
from pylzt.facades._namespace import AntipublicNamespace, ForumNamespace, MarketNamespace
from pylzt.lib.clock import FakeClock
from pylzt.methods.base import BaseMethod, passthrough
from pylzt.token_pool._static import _StaticBearerPool
from pylzt.token_pool.base import BaseTokenPool, Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import ApiTarget, HttpMethod, RateClass, TokenId


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


class _FakeMarketMethod(BaseMethod[str]):
    __api__ = ApiTarget.MARKET
    __http_method__ = HttpMethod.GET
    __url__ = "/x"
    __returning__ = passthrough


class _FakeForumMethod(BaseMethod[str]):
    __api__ = ApiTarget.FORUM
    __rate_class__ = RateClass.FORUM
    __http_method__ = HttpMethod.GET
    __url__ = "/y"
    __returning__ = passthrough


class _FakeAntipublicMethod(BaseMethod[str]):
    __api__ = ApiTarget.ANTIPUBLIC
    __rate_class__ = RateClass.ANTIPUBLIC
    __http_method__ = HttpMethod.GET
    __url__ = "/z"
    __returning__ = passthrough


class _RecordingTransport(BaseTransport):
    def __init__(self, token_pool: BaseTokenPool | None = None) -> None:
        super().__init__(token_pool=token_pool or _pool())
        self.sent: list[Request] = []

    async def _send_raw(self, req: Request) -> Response:
        self.sent.append(req)
        return Response(status=200, body={"ok": True})

    async def aclose(self) -> None:
        return None


async def test_namespaces_have_correct_types() -> None:
    async with Client(tokens=["tok"]) as client:
        assert isinstance(client.market, MarketNamespace)
        assert isinstance(client.forum, ForumNamespace)
        assert isinstance(client.antipublic, AntipublicNamespace)


async def test_market_namespace_execute_delegates() -> None:
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        result = await client.market.execute(_FakeMarketMethod())
    assert result == {"ok": True}
    assert transport.sent[0].path == "/x"


async def test_market_namespace_call_delegates() -> None:
    """Every generated facade method body calls `self(...)`, not `self.execute(...)`."""
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        result = await client.market(_FakeMarketMethod())
    assert result == {"ok": True}


async def test_forum_namespace_delegates() -> None:
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], forum_transport=transport) as client:
        result = await client.forum.execute(_FakeForumMethod())
    assert result == {"ok": True}
    assert transport.sent[0].path == "/y"


async def test_antipublic_namespace_delegates_with_key() -> None:
    transport = _RecordingTransport(token_pool=_StaticBearerPool(key="k"))
    async with Client(tokens=["tok"], antipublic_key="k", antipublic_transport=transport) as client:
        result = await client.antipublic.execute(_FakeAntipublicMethod())
    assert result == {"ok": True}
    assert transport.sent[0].path == "/z"


async def test_antipublic_without_key_still_constructs_namespace() -> None:
    async with Client(tokens=["tok"]) as client:
        assert isinstance(client.antipublic, AntipublicNamespace)


async def test_antipublic_call_without_key_raises_credential_missing_not_attribute_error() -> None:
    async with Client(tokens=["tok"]) as client:
        with pytest.raises(CredentialMissing) as exc_info:
            await client.antipublic.execute(_FakeAntipublicMethod())
    assert exc_info.value.credential == "antipublic_key"


def test_client_config_antipublic_defaults() -> None:
    config = ClientConfig()
    assert config.antipublic_base_url == "https://antipublic.one/api/v2"
    assert config.antipublic_per_min == 60

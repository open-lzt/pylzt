"""The `BaseTransport.send()` rail: signing, rate-class leasing, retry-on-typed-error."""

from __future__ import annotations

import pytest

from pylzt.client import Client
from pylzt.errors import AuthFailed, RateLimited
from pylzt.lib.clock import FakeClock
from pylzt.lib.retry import BaseRetryPolicy, ExponentialBackoff
from pylzt.token_pool.base import BaseTokenPool, Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import RateClass, TokenId


class MemoryTransport(BaseTransport):
    """Records requests; replays a scripted list of Responses or exceptions."""

    def __init__(
        self,
        script: list[Response | Exception],
        *,
        token_pool: BaseTokenPool,
        retry: BaseRetryPolicy | None = None,
        enable_server_rate_sync: bool = True,
    ) -> None:
        super().__init__(
            token_pool=token_pool, retry=retry, enable_server_rate_sync=enable_server_rate_sync
        )
        self.script = script
        self.seen: list[Request] = []

    async def _send_raw(self, req: Request) -> Response:
        self.seen.append(req)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _client(
    script: list[Response | Exception],
    *,
    retry: BaseRetryPolicy | None = None,
    enable_server_rate_sync: bool = True,
) -> tuple[Client, MemoryTransport]:
    clock = FakeClock()
    pool = RoundRobinTokenPool(
        [Token(token_id=TokenId("tok0"), credential="secret-cred")], clock=clock
    )
    transport = MemoryTransport(
        script, token_pool=pool, retry=retry, enable_server_rate_sync=enable_server_rate_sync
    )
    client = Client(token_pool=pool, transport=transport, clock=clock)
    return client, transport


async def test_send_signs_bearer_and_rate_class() -> None:
    client, transport = _client([Response(status=200, body={"ok": True})])
    req = Request(method="GET", path="/steam", rate_class=RateClass.SEARCH)
    resp = await client._transport.send(req)

    assert resp.body == {"ok": True}
    assert transport.seen[0].bearer == "secret-cred"  # leased token signed in
    assert transport.seen[0].rate_class is RateClass.SEARCH


async def test_send_retries_then_succeeds() -> None:
    client, transport = _client(
        [RateLimited(retry_after=0.0), Response(status=200, body={"ok": 1})],
        retry=ExponentialBackoff(base=0.0, max_attempts=3),
    )
    resp = await client._transport.send(
        Request(method="GET", path="/", rate_class=RateClass.GENERAL)
    )

    assert resp.body == {"ok": 1}
    assert len(transport.seen) == 2  # one retry


async def test_auth_failure_is_terminal_and_quarantines() -> None:
    client, transport = _client(
        [AuthFailed(TokenId("tok0"))], retry=ExponentialBackoff(max_attempts=3)
    )
    with pytest.raises(AuthFailed):
        await client._transport.send(Request(method="GET", path="/", rate_class=RateClass.GENERAL))
    assert len(transport.seen) == 1  # no retry on a terminal auth error


async def test_successful_response_reconciles_rate_limit_snapshot() -> None:
    body = {
        "ok": True,
        "system_info": {"rate_limit": {"limit": 120, "remaining": 7, "reset": 0}},
    }
    client, _transport = _client([Response(status=200, body=body)])
    token_id = client._token_pool._tokens[0].token_id  # type: ignore[attr-defined]

    await client._transport.send(Request(method="GET", path="/", rate_class=RateClass.GENERAL))

    bucket_set = client._token_pool._buckets[token_id]  # type: ignore[attr-defined]
    assert bucket_set._select(RateClass.GENERAL).available(client._clock) == 7


async def test_rate_sync_toggle_off_skips_reconcile() -> None:
    body = {
        "ok": True,
        "system_info": {"rate_limit": {"limit": 120, "remaining": 7, "reset": 0}},
    }
    client, _transport = _client([Response(status=200, body=body)], enable_server_rate_sync=False)
    token_id = client._token_pool._tokens[0].token_id  # type: ignore[attr-defined]

    await client._transport.send(Request(method="GET", path="/", rate_class=RateClass.GENERAL))

    bucket_set = client._token_pool._buckets[token_id]  # type: ignore[attr-defined]
    # untouched by reconcile — only down by the lease's own 1-token consume,
    # not clamped to the server-reported 7
    assert bucket_set._select(RateClass.GENERAL).available(client._clock) == 119


async def test_response_without_system_info_leaves_budget_untouched() -> None:
    client, _transport = _client([Response(status=200, body={"ok": True})])
    token_id = client._token_pool._tokens[0].token_id  # type: ignore[attr-defined]

    await client._transport.send(Request(method="GET", path="/", rate_class=RateClass.GENERAL))

    bucket_set = client._token_pool._buckets[token_id]  # type: ignore[attr-defined]
    # only down by the lease's own 1-token consume — no reconcile happened
    assert bucket_set._select(RateClass.GENERAL).available(client._clock) == 119

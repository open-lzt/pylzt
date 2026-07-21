"""Per-call request options: the transport layer, where the feature is either real or nothing.

Everything above this — method classes, facades, the generator — only threads the object through.
If the wire call ignores it, the whole feature is decoration, so it is proven here first.
"""

from __future__ import annotations

from typing import Any

import pytest

from pylzt.errors import LztError, TotalTimeoutExceeded, TransportError
from pylzt.lib.clock import FakeClock
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, RequestOptions, Response
from pylzt.transport.session import HttpxSession
from pylzt.token_pool.base import Token, TokenId
from pylzt.types import RateClass

pytestmark = pytest.mark.anyio


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


def _request(**kwargs: Any) -> Request:
    base: dict[str, Any] = {"method": "GET", "path": "/x", "rate_class": RateClass.GENERAL}
    return Request(**{**base, **kwargs})


def test_an_authorization_header_is_refused_at_construction() -> None:
    """The pool leases the token and accounts the outcome against it — including quarantine on a
    401. A caller-supplied Authorization would send the call as a different identity while the
    pool still blamed the leased one."""
    with pytest.raises(ValueError, match="Authorization"):
        RequestOptions(headers={"Authorization": "Bearer someone-else"})


def test_the_refusal_is_case_insensitive() -> None:
    """HTTP header names are case-insensitive, so a lowercase spelling is the same override."""
    with pytest.raises(ValueError, match="Authorization"):
        RequestOptions(headers={"authorization": "Bearer someone-else"})


def test_ordinary_headers_are_accepted() -> None:
    assert RequestOptions(headers={"X-Trace": "abc"}).headers == {"X-Trace": "abc"}


class _AlwaysRetryable(BaseTransport):
    """Fails with a retryable error forever, so only a deadline can end the loop."""

    def __init__(self) -> None:
        super().__init__(token_pool=_pool())
        self.attempts = 0

    async def _send_raw(self, req: Request) -> Response:
        self.attempts += 1
        raise TransportError(status=503)


async def test_total_timeout_ends_a_retry_chain_that_would_otherwise_continue() -> None:
    """`timeout` bounds one attempt and says nothing about how many there will be. This is the
    only setting that answers "finish within N seconds"."""
    transport = _AlwaysRetryable()
    req = _request(options=RequestOptions(total_timeout=0.25))

    with pytest.raises(TotalTimeoutExceeded) as caught:
        await transport.send(req)

    assert caught.value.total_timeout == 0.25
    assert caught.value.attempts >= 1
    assert transport.attempts >= 1


async def test_the_deadline_error_is_not_a_retryable_upstream_signal() -> None:
    """It is client-side and terminal: retrying is precisely what a spent budget forbids, so it
    must not be mistaken for the wire errors the retry policy acts on."""
    assert issubclass(TotalTimeoutExceeded, LztError)
    assert TotalTimeoutExceeded.__wire__ is False


async def test_without_a_total_timeout_the_chain_is_left_alone() -> None:
    """The deadline is opt-in — an unset budget must not silently become one."""
    transport = _AlwaysRetryable()

    with pytest.raises(TransportError):
        await transport.send(_request())

    assert transport.attempts >= 1


class _CapturingSession(HttpxSession):
    """Captures the kwargs handed to httpx instead of opening a socket."""

    def __init__(self) -> None:
        super().__init__(base_url="https://example.invalid", token_pool=_pool())
        self.sent: dict[str, Any] = {}

        class _Client:
            async def request(_self, method: str, path: str, **kwargs: Any) -> Any:
                self.sent = {"method": method, "path": path, **kwargs}

                class _Raw:
                    status_code = 200
                    headers: dict[str, str] = {}
                    content = b"{}"

                    def json(_s) -> dict[str, Any]:
                        return {}

                return _Raw()

        self._clients[None] = _Client()  # type: ignore[assignment]

    def _client_for(self, proxy: Any) -> Any:
        return self._clients[None]


async def test_headers_cookies_and_params_reach_the_wire_call() -> None:
    session = _CapturingSession()
    options = RequestOptions(
        headers={"X-Trace": "abc"}, cookies={"sid": "s1"}, params={"extra": "1"}
    )

    await session._do_wire_send(_request(bearer="tok", options=options))

    assert session.sent["headers"]["X-Trace"] == "abc"
    assert session.sent["cookies"] == {"sid": "s1"}
    # A list of pairs, not a mapping — that is how a repeated `key[]` parameter survives encoding.
    assert ("extra", "1") in session.sent["params"]


async def test_the_leased_token_still_wins_over_any_caller_header() -> None:
    """Belt and braces beside the validator: whichever path built the options, the Authorization
    the pool leased is the one that goes out."""
    session = _CapturingSession()
    options = RequestOptions.model_construct(headers={"Authorization": "Bearer forged"})

    await session._do_wire_send(_request(bearer="real-token", options=options))

    assert session.sent["headers"]["Authorization"] == "Bearer real-token"


async def test_a_caller_param_overrides_the_one_the_method_computed() -> None:
    """Passing a param the method also sets is a deliberate override, not an accident — and the
    method's own value must be GONE, not merely followed by the override."""
    session = _CapturingSession()

    await session._do_wire_send(
        _request(query={"page": 1}, options=RequestOptions(params={"page": 9}))
    )

    assert session.sent["params"] == [("page", 9)]


async def test_a_per_attempt_timeout_is_passed_through() -> None:
    session = _CapturingSession()

    await session._do_wire_send(_request(options=RequestOptions(timeout=7.5)))

    assert session.sent["timeout"] == 7.5


async def test_no_timeout_option_leaves_the_session_default_untouched() -> None:
    """httpx reads an explicit `timeout=None` as "no timeout at all", so the kwarg must be absent
    rather than None — otherwise every optionless call would silently lose the session's own."""
    session = _CapturingSession()

    await session._do_wire_send(_request())

    assert "timeout" not in session.sent


async def test_a_repeated_parameter_is_not_collapsed_by_the_merge() -> None:
    """`_flatten_query` encodes a list as several `key[]` pairs. Merging through a dict would keep
    only the last one and silently narrow the query."""
    session = _CapturingSession()

    await session._do_wire_send(
        _request(query={"email_type": ["a", "b"]}, options=RequestOptions(params={"page": 1}))
    )

    assert session.sent["params"].count(("email_type[]", "a")) == 1
    assert session.sent["params"].count(("email_type[]", "b")) == 1
    assert ("page", 1) in session.sent["params"]

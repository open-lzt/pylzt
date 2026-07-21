"""Transport seam — the only place the wire shape is allowed to exist.

`BaseTransport` exchanges our own frozen `Request`/`Response` DTOs, never
raw `httpx.*` types (Law 18). A backend swap (`HttpxSession` → own-reverse / Go
core) touches only a concrete impl; everything above the seam is unaffected.

`BaseTransport.send()` is a concrete template method: lease a token (rate
class) -> bind its sticky proxy -> sign -> `_send_raw()` (the abstract wire
hook) -> on a typed error apply the retry policy and report proxy/token
health -> return the `Response`. Sign + rate-limit + retry are always the
same order, so it lives once here instead of in a second wrapping
`BaseTransport` (former `RateLimitedTransport`, removed) — every concrete
transport gets lease/retry/gate for free by implementing only `_send_raw`.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pylzt.errors import (
    AuthFailed,
    LztError,
    ProxyChallenge,
    TotalTimeoutExceeded,
    TransportError,
)
from pylzt.lib.clock import Clock, RealClock
from pylzt.lib.metrics import BaseMetrics, NullMetrics
from pylzt.lib.retry import BaseRetryPolicy, ExponentialBackoff
from pylzt.media import Media
from pylzt.token_pool.governor import BaseConcurrencyGovernor, NullConcurrencyGovernor
from pylzt.token_pool.rate_limit import RateLimitSnapshot
from pylzt.types import ProxyOutcome, ProxyScheme, RateClass

if TYPE_CHECKING:
    from pylzt.token_pool.base import BaseTokenPool, Lease


class ProxySpec(BaseModel):
    """Proxy descriptor handed to the transport. Credentials never hit a log."""

    model_config = ConfigDict(frozen=True)

    scheme: ProxyScheme
    host: str
    port: int
    username: str | None = None
    password: str | None = None


class RequestOptions(BaseModel):
    """Transport overrides for ONE call — headers, cookies, extra query params, timeouts.

    Bundled rather than spread across keyword arguments on every generated method, and that is not
    a style choice: the three OpenAPI specs declare 629 distinct parameter names, and `cookies` is
    already one of them (two endpoints), `extra` another (three). A flattened `cookies=` argument
    would collide with a real endpoint's own parameter. One bundle collides with nothing.

    The two timeouts answer different questions and neither implies the other:

    * ``timeout`` bounds a SINGLE HTTP attempt — httpx's own meaning, applied per try.
    * ``total_timeout`` bounds the whole chain: every retry plus every backoff sleep between them.
      Exceeding it raises `TotalTimeoutExceeded`, which is not retryable by construction.

    A call that must finish within N seconds needs ``total_timeout``; ``timeout`` alone bounds one
    attempt and says nothing about how many there will be.
    """

    model_config = ConfigDict(frozen=True)

    headers: Mapping[str, str] | None = None
    cookies: Mapping[str, str] | None = None
    # Merged into the method's own query string; on a key clash these win, since the caller is
    # deliberately overriding what the method computed.
    params: Mapping[str, Any] | None = None
    timeout: float | None = None
    total_timeout: float | None = None

    @field_validator("headers")
    @classmethod
    def _refuse_authorization(cls, value: Mapping[str, str] | None) -> Mapping[str, str] | None:
        """Authorization is the token pool's to set, and only the pool knows which token was leased.

        Letting a caller pass it would send the request as somebody else while the pool still
        accounted the call — including quarantine on a 401 — against the token it leased. Refused
        loudly instead of being silently dropped, so the caller learns the header did nothing.
        """
        if value is None:
            return None
        for key in value:
            if key.lower() == "authorization":
                raise ValueError(
                    "Authorization is set from the leased token and cannot be overridden per call"
                )
        return value


class Request(BaseModel):
    """A wire-agnostic request the transport turns into an actual HTTP call."""

    model_config = ConfigDict(frozen=True)

    method: str
    path: str
    rate_class: RateClass
    query: dict[str, Any] = Field(default_factory=dict)
    # A flat list body is real — POST /batch takes a bare JSON array of jobs, not
    # a {"key": [...]} envelope (verified live 2026-07-03).
    json_body: dict[str, Any] | list[Any] | None = None
    files: dict[str, Media] | None = None
    bearer: str | None = None
    proxy: ProxySpec | None = None
    options: RequestOptions | None = None


class Response(BaseModel):
    """A wire-agnostic response. `body` is already-decoded JSON, never raw bytes.

    `text` is set only when the wire body wasn't a JSON object — a handful of
    endpoints (`ListDownload`, `ManagingSteamPreview`, `PublicCountLinesPlain`)
    declare a `text/html`/`text/plain` 200 response whose schema is a bare string,
    not JSON; `body` stays `{}` for these (there's no dict to decode) and `text`
    carries the real payload instead. `BaseMethod.parse_response`'s `passthrough`
    branch prefers `text` over `body` when it's set.
    """

    model_config = ConfigDict(frozen=True)

    status: int
    body: dict[str, Any]
    text: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class BaseTransport(ABC):
    """Send a `Request`, get a `Response` — `send()` leases/signs/retries/gates around
    the abstract `_send_raw()` wire hook. If `token_pool` is never wired in by a
    concrete transport that needs it, `send()` still works — lease/retry/gate are
    policy on top of `_send_raw`, not a precondition for calling it."""

    def __init__(
        self,
        *,
        token_pool: BaseTokenPool,
        retry: BaseRetryPolicy | None = None,
        metrics: BaseMetrics | None = None,
        clock: Clock | None = None,
        enable_server_rate_sync: bool = True,
        concurrency_governor: BaseConcurrencyGovernor | None = None,
    ) -> None:
        self._token_pool = token_pool
        self._retry = retry or ExponentialBackoff()
        self._metrics = metrics or NullMetrics()
        self._clock = clock or RealClock()
        self._enable_server_rate_sync = enable_server_rate_sync
        self._concurrency_governor = concurrency_governor or NullConcurrencyGovernor()

    def set_token_pool(self, token_pool: BaseTokenPool) -> None:
        """Hot-swap the token pool backing this transport (library-design Law 28 —
        no restart needed for an account/proxy rotation)."""
        self._token_pool = token_pool

    async def send(self, req: Request) -> Response:
        total = req.options.total_timeout if req.options else None
        if total is None:
            return await self._send_attempts(req)
        # Bounds the ENTIRE loop below — attempts and the backoff sleeps between them — which is
        # the only place a caller's "finish within N seconds" can be honoured. A per-attempt
        # timeout cannot: it says nothing about how many attempts the retry policy will make.
        try:
            async with asyncio.timeout(total):
                return await self._send_attempts(req)
        except TimeoutError as exc:
            raise TotalTimeoutExceeded(total_timeout=total, attempts=self._attempts_made) from exc

    async def _send_attempts(self, req: Request) -> Response:
        attempt = 0
        self._attempts_made = 0
        while True:
            self._attempts_made = attempt + 1
            async with (
                self._concurrency_governor.gate(req.rate_class).acquire(),
                self._token_pool.lease(req.rate_class) as lease,
            ):
                signed = req.model_copy(
                    update={
                        "bearer": lease.token.credential,
                        "proxy": lease.proxy.to_spec() if lease.proxy else None,
                    }
                )
                try:
                    resp = await self._send_raw(signed)
                except LztError as exc:
                    self._report_outcome(lease, exc)
                    delay = self._retry.next_delay(attempt, exc)
                    if delay is None:
                        raise
                    attempt += 1
                else:
                    if lease.proxy is not None:
                        self._token_pool.report_proxy(lease.proxy, ProxyOutcome.OK)
                    if self._enable_server_rate_sync:
                        snapshot = RateLimitSnapshot.from_body(resp.body)
                        if snapshot is not None:
                            self._token_pool.report_rate_limit(
                                lease.token.token_id, req.rate_class, snapshot
                            )
                            self._concurrency_governor.observe(req.rate_class, snapshot)
                    return resp
            await asyncio.sleep(delay)

    @abstractmethod
    async def _send_raw(self, req: Request) -> Response:
        """Execute the already-leased-and-signed call. Raises a typed `LztError` on a
        narrowed upstream signal."""

    def _report_outcome(self, lease: Lease, exc: LztError) -> None:
        if isinstance(exc, AuthFailed):
            self._token_pool.quarantine(lease.token.token_id)
        if lease.proxy is None:
            return
        if isinstance(exc, ProxyChallenge):
            self._token_pool.report_proxy(lease.proxy, ProxyOutcome.BANNED)
        elif isinstance(exc, TransportError):
            self._token_pool.report_proxy(lease.proxy, ProxyOutcome.TIMEOUT)

    async def aclose(self) -> None:
        """Release any held connections. Default no-op for stateless backends."""

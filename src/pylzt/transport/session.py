"""`HttpxSession` — the SDK's only `BaseTransport`, backed by httpx with a request
middleware chain.

Bearer auth is a plain `Authorization` header (confirmed 2026-07-03 by reading AS7's
own `.request()` source before it was deleted: no signing/nonce/HMAC beyond that).
List/dict query-param values are flattened PHP/XenForo-style (`key[]=v1&key[]=v2`,
`key[k]=v`) — httpx's default query encoding doesn't do this, and
`LotFilter.to_query()`'s `game` filter genuinely sends a list, so this must happen
here or a game-filtered search silently breaks.

Proxy is bound at httpx client CONSTRUCTION (no per-request proxy on a shared
client), so one `httpx.AsyncClient` is pooled per distinct `req.proxy` (`None` keys
the direct/no-proxy client).

    session = HttpxSession(base_url="https://prod-api.lzt.market", token_pool=pool)
    session.request_middlewares.register(MyLoggingMiddleware())
    client = Client(tokens=[...], transport=session)   # methods now ride this session
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pylzt.errors import DependencyMissing, LztError
from pylzt.transport.base import BaseTransport, Response
from pylzt.transport.middleware import BaseMiddleware, MiddlewareManager

if TYPE_CHECKING:
    from collections.abc import Sequence

    import httpx

    from pylzt.lib.clock import Clock
    from pylzt.lib.metrics import BaseMetrics
    from pylzt.lib.retry import BaseRetryPolicy
    from pylzt.token_pool.base import BaseTokenPool
    from pylzt.token_pool.governor import BaseConcurrencyGovernor
    from pylzt.transport.base import ProxySpec, Request


def _decode(response: Any) -> tuple[dict[str, Any], str | None]:
    """(body, text) — text is set whenever the wire body isn't a JSON object, so a
    non-JSON 200 (e.g. the bare-string `text/html`/`text/plain` responses declared
    by ListDownload/ManagingSteamPreview/PublicCountLinesPlain) doesn't silently
    collapse to `{}` with no way to recover the real payload."""
    try:
        data = response.json()
    except (ValueError, TypeError):
        return {}, response.text
    return (data, None) if isinstance(data, dict) else ({}, response.text)


def _flatten_query(params: dict[str, Any]) -> list[tuple[str, Any]]:
    """PHP/XenForo array encoding the API expects: lists -> `key[]`, dicts -> `key[k]`."""
    pairs: list[tuple[str, Any]] = []
    for key, value in params.items():
        if isinstance(value, list | tuple):
            pairs.extend((f"{key}[]", item) for item in value)
        elif isinstance(value, dict):
            pairs.extend((f"{key}[{k}]", v) for k, v in value.items())
        else:
            pairs.append((key, value))
    return pairs


def _render_proxy(spec: ProxySpec | None) -> str | None:
    if spec is None:
        return None
    auth = f"{spec.username}:{spec.password or ''}@" if spec.username else ""
    return f"{spec.scheme.value}://{auth}{spec.host}:{spec.port}"


class HttpxSession(BaseTransport):
    """An httpx `BaseTransport` whose request path runs through a middleware chain."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 90.0,
        middlewares: Sequence[BaseMiddleware] = (),
        client: httpx.AsyncClient | None = None,
        token_pool: BaseTokenPool,
        retry: BaseRetryPolicy | None = None,
        metrics: BaseMetrics | None = None,
        clock: Clock | None = None,
        enable_server_rate_sync: bool = True,
        concurrency_governor: BaseConcurrencyGovernor | None = None,
    ) -> None:
        super().__init__(
            token_pool=token_pool,
            retry=retry,
            metrics=metrics,
            clock=clock,
            enable_server_rate_sync=enable_server_rate_sync,
            concurrency_governor=concurrency_governor,
        )
        self._base_url = base_url
        self._timeout = timeout
        # aiogram-style registry; also a decorator: `@session.request_middlewares`.
        self.request_middlewares = MiddlewareManager()
        for middleware in middlewares:
            self.request_middlewares.register(middleware)
        # Keyed by rendered proxy URL (None = direct); `client` seeds the direct slot
        # (test injection / an already-configured caller-owned client).
        self._clients: dict[str | None, httpx.AsyncClient] = {}
        if client is not None:
            self._clients[None] = client

    async def _send_raw(self, req: Request) -> Response:
        return await self.request_middlewares.dispatch(req, self._do_wire_send)

    async def _do_wire_send(self, req: Request) -> Response:
        client = self._client_for(req.proxy)
        opts = req.options
        # Caller headers first, Authorization stamped on top. RequestOptions already refuses an
        # Authorization key, so this is belt and braces: the leased token is never overridable,
        # whichever path built the options.
        headers: dict[str, str] | None = dict(opts.headers) if opts and opts.headers else None
        if req.bearer:
            headers = {**(headers or {}), "Authorization": f"Bearer {req.bearer}"}
        cookies = dict(opts.cookies) if opts and opts.cookies else None
        params = _flatten_query(req.query) if req.query else None
        if opts and opts.params:
            # A LIST of pairs, not a dict: `_flatten_query` encodes a repeated parameter as several
            # `key[]` entries, and collapsing that to a mapping would keep only the last of them.
            # Caller wins on a clash — passing a param the method also computes is a deliberate
            # override — so its keys are dropped from the method's pairs before the caller's are
            # appended, and the caller's own list values go through the same PHP-array encoding.
            override = _flatten_query(dict(opts.params))
            overridden = {key for key, _ in override}
            params = [(k, v) for k, v in (params or []) if k not in overridden] + override
        # Passed only when the caller actually set one. httpx reads an explicit `timeout=None` as
        # "no timeout at all", so defaulting the kwarg to None would silently strip the session's
        # own — and httpx is a lazy optional import here, so its USE_CLIENT_DEFAULT sentinel is not
        # in scope to name either. Omitting the kwarg is what "leave the default alone" looks like.
        extra: dict[str, Any] = {}
        if opts and opts.timeout is not None:
            extra["timeout"] = opts.timeout
        if req.files:
            files = {field: (m.filename, m.data, m.content_type) for field, m in req.files.items()}
            # httpx forbids json= together with files= (content-type conflict) — the
            # non-file fields ride as multipart form data instead. A multipart body is
            # always a flat field map (never the /batch-style bare JSON array), so
            # json_body here is a dict or None — see BaseMethod.build_request.
            data = req.json_body if isinstance(req.json_body, dict) else None
            raw = await client.request(
                req.method,
                req.path,
                params=params,
                data=data,
                files=files,
                headers=headers,
                cookies=cookies,
                **extra,
            )
        else:
            raw = await client.request(
                req.method,
                req.path,
                params=params,
                json=req.json_body,
                headers=headers,
                cookies=cookies,
                **extra,
            )
        body, text = _decode(raw)
        err = LztError.match(raw.status_code, dict(raw.headers), body)
        if err is not None:
            raise err
        return Response(status=raw.status_code, body=body, text=text, headers=dict(raw.headers))

    def _client_for(self, proxy: ProxySpec | None) -> httpx.AsyncClient:
        key = _render_proxy(proxy)
        client = self._clients.get(key)
        if client is None:
            try:
                import httpx
            except ImportError as exc:
                raise DependencyMissing(extra="httpx") from exc
            client = httpx.AsyncClient(
                base_url=self._base_url or "", timeout=self._timeout, proxy=key
            )
            self._clients[key] = client
        return client

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

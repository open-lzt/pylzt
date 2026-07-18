"""Request middleware — swappable, composable policies around a transport send.

Each middleware is an onion layer: it receives the `Request` and a `call_next`
that runs the rest of the chain (ending in the actual transport send), and returns
a `Response`. It may short-circuit, retry, enrich the request, or map/raise on the
response — which is how a consumer plugs in error handling without touching the
transport.

Registration is aiogram-style via `MiddlewareManager` (the session exposes one as
`request_middlewares`): the manager is itself a decorator. First registered =
outermost wrapper; the chain rebuilds per dispatch so register/unregister is
immediately visible.

    @session.request_middlewares                       # decorate a subclass …
    class RaiseOnBusinessError(BaseMiddleware):
        async def __call__(self, request: Request, call_next: Next) -> Response:
            resp = await call_next(request)
            if resp.body.get("status") == "error":
                raise UpstreamRejected(resp.body)       # the consumer's own typed error
            return resp

    session.request_middlewares.register(LoggingMiddleware())   # … or register an instance
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Iterator
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pylzt.transport.base import Request, Response

Next = Callable[["Request"], Awaitable["Response"]]

_log = structlog.get_logger("pylzt.transport")


class BaseMiddleware(ABC):
    """One layer around a transport send. Compose many into a chain."""

    @abstractmethod
    async def __call__(self, request: Request, call_next: Next) -> Response:
        """Process `request`; call `call_next(request)` to continue the chain."""


class LoggingMiddleware(BaseMiddleware):
    """Reference passthrough: logs each request's method/path and resulting status."""

    async def __call__(self, request: Request, call_next: Next) -> Response:
        response = await call_next(request)
        _log.debug("request", method=request.method, path=request.path, status=response.status)
        return response


def stable_id(target: BaseMiddleware | type[BaseMiddleware]) -> str:
    """Dedup key — `"<module>.<qualname>"`. Two instances of one class collide."""
    cls = target if isinstance(target, type) else type(target)
    return f"{cls.__module__}.{cls.__qualname__}"


def _wrap(middleware: BaseMiddleware, call_next: Next) -> Next:
    async def call(request: Request) -> Response:
        return await middleware(request, call_next)

    return call


class MiddlewareManager:
    """Aiogram-style ordered, dedup'd registry of request middlewares.

    Callable as a decorator over a `BaseMiddleware` subclass or instance. The chain
    is rebuilt on every `dispatch`, so registering / unregistering takes effect at
    once. First registered is the outermost wrapper (aiogram / Starlette convention).
    """

    def __init__(self) -> None:
        self._items: list[BaseMiddleware] = []
        self._ids: set[str] = set()

    def register(self, middleware: BaseMiddleware) -> BaseMiddleware:
        """Append `middleware`; a second instance of the same class is a no-op."""
        sid = stable_id(middleware)
        if sid not in self._ids:
            self._ids.add(sid)
            self._items.append(middleware)
        return middleware

    def __call__[M: BaseMiddleware](self, target: M | type[M]) -> M | type[M]:
        middleware: BaseMiddleware = target() if isinstance(target, type) else target
        self.register(middleware)
        return target

    def unregister(self, target: BaseMiddleware | str) -> bool:
        """Remove by instance or stable id. Returns False if it wasn't registered."""
        sid = target if isinstance(target, str) else stable_id(target)
        if sid not in self._ids:
            return False
        self._ids.discard(sid)
        self._items = [m for m in self._items if stable_id(m) != sid]
        return True

    @property
    def middlewares(self) -> tuple[BaseMiddleware, ...]:
        return tuple(self._items)

    def __iter__(self) -> Iterator[BaseMiddleware]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, BaseMiddleware):
            return stable_id(item) in self._ids
        if isinstance(item, str):
            return item in self._ids
        return False

    async def dispatch(self, request: Request, terminal: Next) -> Response:
        """Run the registered chain wrapped around `terminal` and return its result."""
        handler = terminal
        for middleware in reversed(self._items):
            handler = _wrap(middleware, handler)
        return await handler(request)

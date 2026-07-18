"""Token-pool contract — the one place rate-limit lives.

A request declares its `RateClass`; the pool blocks until a token with budget in
that class is free, binds that token's sticky proxy, and yields a `Lease`. No
caller ever touches a raw bucket or sleeps on its own — this kills the
ecosystem's duplicated-poller anti-pattern (`00-audit.md`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager

from pydantic import BaseModel, ConfigDict

from pylzt.proxy_pool.base import Proxy
from pylzt.token_pool.rate_limit import RateLimitSnapshot
from pylzt.types import ProxyOutcome, RateClass, TokenId


class Token(BaseModel):
    model_config = ConfigDict(frozen=True)

    token_id: TokenId
    credential: str


class Lease(BaseModel):
    """A leased (token, proxy) pair. The proxy is bound for the request's life."""

    model_config = ConfigDict(frozen=True)

    token: Token
    proxy: Proxy | None


class BaseTokenPool(ABC):
    @abstractmethod
    def lease(self, rate_class: RateClass) -> AbstractAsyncContextManager[Lease]:
        """Block until a token has `rate_class` budget, then yield a bound lease."""

    def report_proxy(self, proxy: Proxy, outcome: ProxyOutcome) -> None:
        """Forward a request outcome to the bound proxy's health. Default no-op."""

    def quarantine(self, token_id: TokenId) -> None:
        """Pull a token out of rotation (token health §5). Default no-op."""

    def report_rate_limit(
        self, token_id: TokenId, rate_class: RateClass, snapshot: RateLimitSnapshot
    ) -> None:
        """Reconcile local budget with server ground truth. Default no-op."""

    async def aclose(self) -> None:
        """Release pool resources (proxy sources, etc.). Default no-op."""

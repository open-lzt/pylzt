"""Proxy-pool contract — the per-IP budget multiplier made explicit.

The N* rate budget collapses the instant two live tokens share an exit IP (D29),
so proxy assignment is a first-class seam, not a loose `proxy=` arg. A pool pins
one healthy proxy per token (`StickyProxyPool`) and the lease travels into the
transport — never onto a public DTO. Only the opaque `proxy_id` is ever logged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, SecretStr

from pylzt.transport.base import ProxySpec
from pylzt.types import ProxyId, ProxyScheme

if TYPE_CHECKING:
    from collections.abc import Sequence
    from contextlib import AbstractAsyncContextManager

    from pylzt.types import ProxyOutcome, TokenId


class ProxyAuth(BaseModel):
    model_config = ConfigDict(frozen=True)

    username: str
    password: SecretStr


class Proxy(BaseModel):
    """A proxy endpoint. `proxy_id` is the only field allowed on logs/metrics."""

    model_config = ConfigDict(frozen=True)

    proxy_id: ProxyId
    scheme: ProxyScheme
    host: str
    port: int
    auth: ProxyAuth | None = None

    def to_spec(self) -> ProxySpec:
        """Render to the transport's wire descriptor (credentials included)."""
        return ProxySpec(
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            username=self.auth.username if self.auth else None,
            password=self.auth.password.get_secret_value() if self.auth else None,
        )


class BaseProxySource(ABC):
    """Where proxies come from — static list, file, env, or a provider API."""

    @abstractmethod
    def load(self) -> Sequence[Proxy]: ...


class BaseProxyPool(ABC):
    """Hands out a proxy per token and absorbs health feedback.

    `acquire` is an async context manager so the pool can park a token whose
    pinned proxy is cooling down and release the bulkhead slot on exit.
    """

    @abstractmethod
    def acquire(self, token_id: TokenId) -> AbstractAsyncContextManager[Proxy | None]:
        """Yield the healthy proxy bound to `token_id` (or `None` for direct)."""

    @abstractmethod
    def report(self, proxy_id: ProxyId, outcome: ProxyOutcome) -> None:
        """Feed a request outcome into the per-proxy breaker + cooldown."""

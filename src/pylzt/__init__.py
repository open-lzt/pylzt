"""pylzt — typed, token-pooled async SDK over the lzt.market catalog API.

`import pylzt` performs zero I/O (Law 23): `httpx` is imported lazily only when a
`Client`/`HttpxSession` actually needs it.

`__all__` is the **stable public surface** (Law 17): the facade + DTOs a consumer reads,
and the extension bases a downstream module (e.g. `autobuy`) subclasses — methods,
transport, middleware, cache, token selection, observability. A consumer extends error
narrowing by subclassing `LztError` with `__wire__ = True` (self-registers, see
`errors.py`) rather than injecting a validator. Everything not listed here is private
and free to churn. See `docs/extending.md` for the seam map.
"""

from __future__ import annotations

from pylzt.client import Client
from pylzt.config import ClientConfig
from pylzt.errors import (
    AuthFailed,
    BadRequest,
    CaptchaRequired,
    DependencyMissing,
    ErrorCode,
    Forbidden,
    LztError,
    MethodDeclarationError,
    ModelNotBound,
    NotFound,
    ProxyChallenge,
    RateLimited,
    RetryableUpstream,
    TransportError,
)
from pylzt.lib.cache import BaseCache, MemoryCache
from pylzt.lib.clock import Clock, FakeClock, RealClock
from pylzt.lib.media_storage import BaseMediaStorage, FileMediaStorage, NullMediaStorage
from pylzt.lib.metrics import BaseMetrics, NullMetrics
from pylzt.lib.retry import BaseRetryPolicy, ExponentialBackoff
from pylzt.media import Media
from pylzt.methods.base import BaseMethod
from pylzt.methods.catalog import GetLot, GetLotsBatch, ListLotsPage
from pylzt.methods.categories import CategoryGames, CategoryParams, ListCategories
from pylzt.models.base import BoundModel
from pylzt.models.category import CategoryGame, FilterSchema
from pylzt.models.lot import Lot, LotFilter
from pylzt.pagination import Page, Paginator
from pylzt.proxy_pool.base import BaseProxySource
from pylzt.token_pool.base import BaseTokenPool, Lease, Token
from pylzt.token_pool.selector import BaseTokenSelector, RoundRobinSelector
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.transport.middleware import (
    BaseMiddleware,
    LoggingMiddleware,
    MiddlewareManager,
    Next,
)
from pylzt.transport.session import HttpxSession
from pylzt.types import (
    Category,
    Currency,
    HttpMethod,
    ItemId,
    ItemOrigin,
    OrderBy,
    ProxyId,
    RateClass,
    SellerId,
    TokenId,
)

__all__ = [
    "AuthFailed",
    "BadRequest",
    "BaseCache",
    "BaseMediaStorage",
    "BaseMethod",
    "BaseMetrics",
    "BaseMiddleware",
    "BaseProxySource",
    "BaseRetryPolicy",
    "BaseTokenPool",
    "BaseTokenSelector",
    "BaseTransport",
    "BoundModel",
    "CaptchaRequired",
    "Category",
    "CategoryGame",
    "CategoryGames",
    "CategoryParams",
    "Client",
    "ClientConfig",
    "Clock",
    "Currency",
    "DependencyMissing",
    "ErrorCode",
    "ExponentialBackoff",
    "FakeClock",
    "FileMediaStorage",
    "FilterSchema",
    "Forbidden",
    "GetLot",
    "GetLotsBatch",
    "HttpMethod",
    "HttpxSession",
    "ItemId",
    "ItemOrigin",
    "Lease",
    "ListCategories",
    "ListLotsPage",
    "LoggingMiddleware",
    "Lot",
    "LotFilter",
    "LztError",
    "Media",
    "MemoryCache",
    "MethodDeclarationError",
    "MiddlewareManager",
    "ModelNotBound",
    "Next",
    "NotFound",
    "NullMediaStorage",
    "NullMetrics",
    "OrderBy",
    "Page",
    "Paginator",
    "ProxyChallenge",
    "ProxyId",
    "RateClass",
    "RateLimited",
    "RealClock",
    "Request",
    "Response",
    "RetryableUpstream",
    "RoundRobinSelector",
    "SellerId",
    "Token",
    "TokenId",
    "TransportError",
]

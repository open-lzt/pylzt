# Types — api-namespaces (frozen contract)

## `types.py` additions

```python
class ApiTarget(StrEnum):
    MARKET = "market"
    FORUM = "forum"
    ANTIPUBLIC = "antipublic"

class RateClass(StrEnum):
    GENERAL = "general"
    SEARCH = "search"
    FORUM = "forum"
    ANTIPUBLIC = "antipublic"
```

## `config.py` additions

```python
@dataclass(frozen=True, slots=True)
class ClientConfig:
    # ... existing fields unchanged ...
    antipublic_base_url: str = "https://antipublic.one/api/v2"
    antipublic_per_min: int = 60  # placeholder — T3 confirms real limit shape live
```

## `src/pylzt/token_pool/_static.py` (new)

```python
from __future__ import annotations
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pylzt.token_pool.base import BaseTokenPool, Lease, Token
from pylzt.types import RateClass, TokenId

class _StaticBearerPool(BaseTokenPool):
    """A BaseTokenPool of exactly one fixed credential, no rotation, no rate-class
    buckets beyond a single window for RateClass.ANTIPUBLIC. Exists so
    RateLimitedTransport's lease/sign/retry rail works for AntiPublic without a
    parallel non-pool transport mechanism. Not part of the public API — internal to
    the Client/AntipublicNamespace wiring.

    STANDALONE implementation (W3.5 correction) — does NOT inherit from or call into
    RoundRobinTokenPool/RateBucketSet.standard(): that bucket-set shape is hardcoded to
    exactly 3 named classes (general/search/forum) and a multi-token selector, neither
    of which this single-credential case needs or can cleanly extend. This class
    reimplements a trivial single-window token bucket inline (~60 LOC), inspired by the
    same algorithm shape, not literally sharing code."""

    def __init__(self, key: str, *, per_min: int, clock: "Clock") -> None:
        self._token = Token(token_id=TokenId("antipublic"), credential=key)
        self._per_min = per_min
        self._clock = clock
        # bucket state — exact fields mirror RoundRobinTokenPool's single-token case,
        # see T2 acceptance for the concrete bucket algorithm reused

    @asynccontextmanager
    async def lease(self, rate_class: RateClass) -> AsyncIterator[Lease]:
        ...  # T2: reuse RoundRobinTokenPool's own per-token bucket wait logic for N=1
```

## `src/pylzt/errors.py` addition (W3.5 correction — new, not a `DependencyMissing` reuse)

```python
class CredentialMissing(LztError):
    """A namespace-specific credential (e.g. AntiPublic's license key) was never
    configured on Client, but a method requiring it was called. Distinct from
    DependencyMissing (missing pip package) — this is a missing runtime credential."""

    def __init__(self, credential: str) -> None:
        self.credential = credential
        super().__init__(ErrorCode.CREDENTIAL_MISSING)  # new ErrorCode member
```

## `src/pylzt/facades/_namespace.py` (new — see 00-overview.md for the full body)

```python
class _Namespace:
    def __init__(self, client: "Client") -> None: ...
    async def execute[T](self, method: BaseMethod[T]) -> T: ...

class MarketNamespace(_Namespace, GeneratedMarketFacade):
    async def get_lot(self, item_id: ItemId) -> Lot: ...
    async def get_lots_batch(self, item_ids: Sequence[ItemId]) -> list[Lot]: ...
    def list_lots(self, filter: LotFilter, *, max_pages: int | None = None) -> Paginator[Lot]: ...
    async def list_categories(self) -> list[Category]: ...
    async def category_params(self, category: Category) -> FilterSchema: ...
    async def category_games(self, category: Category) -> list[CategoryGame]: ...

class ForumNamespace(_Namespace, GeneratedForumFacade):
    ...  # no hand-written additions — generated methods only

class AntipublicNamespace(_Namespace, GeneratedAntipublicFacade):
    ...  # no hand-written additions — generated methods only
```

## `client.py` — `Client.__init__` full new signature

```python
def __init__(
    self,
    tokens: Sequence[str | Token] | None = None,
    *,
    antipublic_key: str | None = None,
    transport: BaseTransport | None = None,
    forum_transport: BaseTransport | None = None,
    antipublic_transport: BaseTransport | None = None,
    token_pool: BaseTokenPool | None = None,
    proxy_source: BaseProxySource | None = None,
    retry: BaseRetryPolicy | None = None,
    metrics: BaseMetrics | None = None,
    clock: Clock | None = None,
    category_cache: BaseCache[FilterSchema] | None = None,
    batch_storage: BaseStorage | None = None,
    config: ClientConfig | None = None,
) -> None: ...
```

`Client` no longer inherits `GeneratedMarketFacade`/`GeneratedForumFacade` — plain
`@final class Client:`. Public attributes: `client.market: MarketNamespace`,
`client.forum: ForumNamespace`, `client.antipublic: AntipublicNamespace`.

## Task ownership (owns = produces, consumes = imports as signature-only)

| Task | Owns | Consumes |
|---|---|---|
| T1 | `ApiTarget.ANTIPUBLIC`, `RateClass.ANTIPUBLIC` | — |
| T2 | `_StaticBearerPool` | `BaseTokenPool`, `Token`, `Lease` (signatures only) |
| T3 | codegen `SITES`/`APIS`/`--api` extension | live AntiPublic spec (external) |
| T4 | `facades/antipublic.py`, `models/antipublic/*` (generated output) | T3's codegen changes |
| T5 | `facades/_namespace.py` | T4's `GeneratedAntipublicFacade`, existing market/forum facades |
| T6 | new `Client.__init__` shape | T2 (`_StaticBearerPool`), T5 (namespaces) |
| T7 | moved hand-written market methods on `MarketNamespace` | T5, T6 |
| T8 | updated docs/tests call sites | T6, T7 |

"""Domain-namespace attachment — `client.market`/`.forum`/`.antipublic`.

Composition, not mixin-inheritance-of-Client (`Client` stays a plain composition
root — see `client.py`'s own docstring). Each namespace holds a `Client` reference
and delegates every call back to it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pylzt.facades.antipublic import GeneratedAntipublicFacade
from pylzt.facades.forum import GeneratedForumFacade
from pylzt.facades.market import GeneratedMarketFacade
from pylzt.lib.asyncio_utils import gather_or_raise
from pylzt.lib.batch import MAX_BATCH_JOBS
from pylzt.methods.base import BaseMethod
from pylzt.methods.catalog import GetLot, GetLotsBatch, ListLotsPage
from pylzt.methods.categories import CategoryGames, CategoryParams, ListCategories
from pylzt.models.category import CategoryGame, FilterSchema
from pylzt.models.lot import Lot, LotFilter
from pylzt.pagination import Page, Paginator
from pylzt.types import Category, ItemId

if TYPE_CHECKING:
    from pylzt.client import Client


class _Namespace:
    """Shared delegation base. Every generated facade method body calls
    `self(SomeMethod(...))` — `__call__`, not `self.execute(...)` — and
    `GeneratedXFacade.__call__` is a `TYPE_CHECKING`-only stub, never present at
    runtime. Both `execute` and `__call__` must delegate here, or every generated
    method raises `TypeError: object is not callable` the moment this namespace
    replaces the old mixin-inheritance attachment."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def execute[T](self, method: BaseMethod[T]) -> T:
        return await self._client.execute(method)

    async def __call__[T](self, method: BaseMethod[T]) -> T:
        return await self._client.execute(method)


class MarketNamespace(_Namespace, GeneratedMarketFacade):
    """`client.market.*` — generated market methods + the hand-written read
    convenience surface (`get_lot`, `list_lots`, `category_params`, ...)."""

    def list_lots(
        self,
        filter: LotFilter | None = None,
        *,
        max_pages: int | None = None,
        **filters: object,
    ) -> Paginator[Lot]:
        """A ``LotFilter``, filter kwargs (``list_lots(category=...)``), or nothing for all lots."""
        if filter is None:
            filter = LotFilter(**filters)
        elif filters:
            raise TypeError("list_lots() takes a LotFilter or filter kwargs, not both")

        async def fetch(page: int) -> Page[Lot]:
            return await self.execute(
                ListLotsPage(
                    filter=filter, page=page, per_page_default=self._client.config.per_page
                )
            )

        return Paginator(fetch, start_page=1, max_pages=max_pages)

    async def get_lot(self, item_id: ItemId) -> Lot:
        return await self.execute(GetLot(item_id=item_id))

    async def get_lots_batch(self, item_ids: Sequence[ItemId]) -> list[Lot]:
        """Read N lots via POST /batch, chunked at the server's MAX_BATCH_JOBS cap.

        Chunks run concurrently and results are concatenated in input order — a
        `GetLotsBatch(chunk)` per chunk keeps `BaseMethod`'s one-request contract.
        """
        if not item_ids:
            return []
        chunks = [item_ids[i : i + MAX_BATCH_JOBS] for i in range(0, len(item_ids), MAX_BATCH_JOBS)]
        results = await gather_or_raise(
            self.execute(GetLotsBatch(item_ids=chunk)) for chunk in chunks
        )
        return [lot for chunk_result in results for lot in chunk_result]

    async def list_categories(self) -> list[Category]:
        return await self.execute(ListCategories())

    async def category_params(self, category: Category) -> FilterSchema:
        """Read-through the injected `BaseCache` (TTL `config.category_params_ttl`)."""
        key = category.value
        cached = await self._client._category_cache.get(key)
        if cached is not None:
            return cached
        result = await self.execute(CategoryParams(category=category))
        await self._client._category_cache.set(
            key, result, ttl=self._client.config.category_params_ttl
        )
        return result

    async def category_games(self, category: Category) -> list[CategoryGame]:
        return await self.execute(CategoryGames(category=category))


class ForumNamespace(_Namespace, GeneratedForumFacade):
    """`client.forum.*` — generated forum methods."""


class AntipublicNamespace(_Namespace, GeneratedAntipublicFacade):
    """`client.antipublic.*` — generated AntiPublic methods. Constructed even
    without `antipublic_key`; a call in that state raises `CredentialMissing`,
    not `AttributeError` (see `client.py`)."""

"""Blocking counterparts of `facades/_namespace.py` — `SyncClient.market`/`.forum`/
`.antipublic`. Each wraps the already-constructed async namespace + one shared
`SyncRunner`; every method (generated or hand-written) is a thin
`self._runner.run(self._async.method(...))` call — no second implementation of
rate limiting, retry, or transport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylzt.facades.sync_antipublic import SyncGeneratedAntipublicFacade
from pylzt.facades.sync_forum import SyncGeneratedForumFacade
from pylzt.facades.sync_market import SyncGeneratedMarketFacade

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pylzt.facades._namespace import MarketNamespace
    from pylzt.models.category import CategoryGame, FilterSchema
    from pylzt.models.lot import Lot, LotFilter
    from pylzt.sync.runner import SyncRunner
    from pylzt.types import Category, ItemId


class SyncMarketNamespace(SyncGeneratedMarketFacade):
    """`SyncClient.market` — generated market methods (via `SyncGeneratedMarketFacade`)
    + blocking counterparts of `MarketNamespace`'s hand-written read surface."""

    def __init__(self, async_namespace: MarketNamespace, runner: SyncRunner) -> None:
        super().__init__(async_namespace, runner)
        # Re-narrow: SyncGeneratedMarketFacade.__init__ types `self._async` as the
        # generated base (GeneratedMarketFacade); the hand-written methods below need
        # the narrower MarketNamespace it's always actually constructed with.
        self._async: MarketNamespace = async_namespace

    def get_lot(self, item_id: ItemId) -> Lot:
        return self._runner.run(self._async.get_lot(item_id))

    def get_lots_batch(self, item_ids: Sequence[ItemId]) -> list[Lot]:
        return self._runner.run(self._async.get_lots_batch(item_ids))

    def list_lots(
        self, filter: LotFilter, *, max_pages: int | None = None, limit: int | None = None
    ) -> list[Lot]:
        """Blocking materialization — no `SyncPaginator` exists yet, so this drains
        the async `Paginator` into a plain `list[Lot]` (optionally capped at
        `limit`) instead of streaming, unlike the async `list_lots`."""
        return self._runner.run(
            self._async.list_lots(filter, max_pages=max_pages).collect(limit=limit)
        )

    def list_categories(self) -> list[Category]:
        return self._runner.run(self._async.list_categories())

    def category_params(self, category: Category) -> FilterSchema:
        return self._runner.run(self._async.category_params(category))

    def category_games(self, category: Category) -> list[CategoryGame]:
        return self._runner.run(self._async.category_games(category))


class SyncForumNamespace(SyncGeneratedForumFacade):
    """`SyncClient.forum` — generated forum methods only (no hand-written surface
    on the async `ForumNamespace` to mirror)."""


class SyncAntipublicNamespace(SyncGeneratedAntipublicFacade):
    """`SyncClient.antipublic` — generated AntiPublic methods. Constructed even
    without `antipublic_key`; a call in that state raises `CredentialMissing`
    (same as the async `AntipublicNamespace` — the runner just blocks on it)."""

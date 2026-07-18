"""Catalog read methods — declarative `BaseMethod[T]` operations (no `__init__`).

Each is a frozen dataclass: request fields + class-var metadata. Flat reads (`GetLot`)
lean on the default `build_request`; pagination and `/batch` override it. No mutations
here (buy/publish belong to later verticals); a consumer adds a catalog op by subclassing.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pylzt.lib.batch import _build_batch_request, _parse_batch_body
from pylzt.methods.base import BaseMethod
from pylzt.models.lot import Lot, LotFilter
from pylzt.pagination import Page
from pylzt.transport.base import Request
from pylzt.types import HttpMethod, ItemId, RateClass

if TYPE_CHECKING:
    from pylzt.transport.base import Response


class GetLot(BaseMethod[Lot]):
    """Fetch a single lot (also the engine's disappearance confirm-poll)."""

    __http_method__ = HttpMethod.GET
    __url__ = "/{item_id}"

    item_id: ItemId

    def parse_response(self, response: Response) -> Lot:
        return Lot.from_raw(response.body.get("item", response.body))


class ListLotsPage(BaseMethod[Page[Lot]]):
    """One `search`-class page of a category listing — the unit a `Paginator` pulls."""

    __rate_class__ = RateClass.SEARCH

    filter: LotFilter
    page: int
    per_page_default: int

    def build_request(self) -> Request:
        query = self.filter.to_query()
        query["page"] = self.page
        path = f"/{self.filter.category.value}" if self.filter.category is not None else "/"
        return Request(
            method=self.__http_method__,
            path=path,
            rate_class=self.__rate_class__,
            query=query,
        )

    def parse_response(self, response: Response) -> Page[Lot]:
        lots = Lot.from_raw_many(response.body)
        default = self.per_page_default
        per_page = int(response.body.get("perPage", default) or default)
        return Page(items=lots, has_more=len(lots) >= per_page and len(lots) > 0)


class GetLotsBatch(BaseMethod[list[Lot]]):
    """One POST /batch for up to `lib.batch.MAX_BATCH_JOBS` item_ids; results in input
    order, absent ids skipped.

    Raises `BatchLimitExceeded` past that cap — `Client.get_lots_batch` chunks larger
    lists into several of these, run concurrently. Reach for `BatchExecutor.submit`
    when you need a per-item `NotFound` instead of a silent skip.
    """

    item_ids: Sequence[ItemId]

    def build_request(self) -> Request:
        return _build_batch_request(self.item_ids)

    def parse_response(self, response: Response) -> list[Lot]:
        lots = _parse_batch_body(response.body, self.item_ids)
        return [lots[iid] for iid in self.item_ids if iid in lots]

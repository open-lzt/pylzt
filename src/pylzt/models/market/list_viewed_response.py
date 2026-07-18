"""Hand-patched — codegen declared `totalItemsPrice: str` (required) from the OpenAPI
spec, but a live `/list/viewed` capture (2026-07-05) returns `null`. Reuses the same
`str | int | None` shape already established for this field in `cart_get_response.py` /
`category_response.py` — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject
from pylzt.models.market.list_user_item import ListUserItem


class ListViewedResponse(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/listviewed"""

    items: list[ListUserItem]
    totalItems: int
    totalItemsPrice: str | int | None = None
    hasNextPage: bool
    perPage: int
    page: int
    wasCached: bool
    cacheTTL: int
    lastModified: int
    serverTime: int
    searchUrl: str
    search: str
    stickyItems: list[str]

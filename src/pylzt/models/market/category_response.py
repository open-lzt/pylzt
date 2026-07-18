"""Hand-patched — codegen declared `totalItemsPrice: str` (required) from the OpenAPI
spec, but a live category search (2026-07-05) returns `null` for it when the result set's
combined price isn't computed. Per-item field mismatches (e.g. BattleNetItem) are a much
larger, separate issue — see docs/codegen-runbook.md; this file only fixes the shared
envelope. Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class CategoryResponse[CategoryResponseItemT](LolzObject):
    """Docs: https://lzt-market.readme.io/reference/categorybattlenet"""

    items: list[CategoryResponseItemT]
    totalItems: int
    totalItemsPrice: str | None = None
    hasNextPage: bool
    perPage: int
    page: int
    wasCached: bool
    cacheTTL: int
    lastModified: int
    serverTime: int
    searchUrl: str
    stickyItems: list[str]

"""Hand-patched — codegen declared `items: list[str]` / `totalItemsPrice: str` (required)
from the OpenAPI spec, but live `/fave` and `/user/orders` responses (2026-07-05) return
`items` as full account objects (not strings) and `totalItemsPrice` as `null` OR a bare
`int` (0) depending on the cart/list's contents. `totalItemsPrice` stays loosened
(`str | int | None`) since its shape genuinely varies by cart/list contents and hasn't been
pinned down further.

`items`/`stickyItems` are typed as `BaseItem` (the 11-field common shape — `item_id`/
`item_state`/`category_id`/`title`/`price`/... — shared by all 21 per-game item models under
`models/market/*_item.py`) rather than `dict[str, Any]`. A stricter 21-way union of the full
per-game models (`SteamItem`, `BattleNetItem`, ...) was tried first and REJECTED: those rich
models carry dozens of required fields (`view_count`, `is_sticky`, `seller`, ...) that were
verified against the single-item `GetLot`-style detail endpoints, not against this shared
list/cart-preview shape — list previews commonly return fewer fields than a full detail card,
and a strict union means ANY missing field crashes the entire response's parsing, which is
worse than the `dict[str, Any]` it replaces. `BaseItem` is the one shape actually documented as
common across CartGet/ListFavorites/ListOrders/CategoryAll's shared `items`/`stickyItems`
polymorphism (per readme.io) without over-committing to per-game fields unverified for this
leaner context. Not yet live-verified against an actual capture (no `LZT_E2E_TOKEN` in this
session) — if a live payload turns out to carry more common fields than `BaseItem` has, promote
them; if a live payload is missing even a `BaseItem` field, that's a real spec gap to hand-patch.

Promoting this out of codegen intentionally clashes with the next `dev.codegen build --api
market` (`_guard_no_clobber` now skips this file per-file instead of aborting the whole
install — see docs/codegen-runbook.md).
"""

from __future__ import annotations

from pylzt.models.base import LolzObject
from pylzt.models.market.base_item import BaseItem


class CartGetResponse(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/cartget"""

    items: list[BaseItem]
    totalItems: int
    totalItemsPrice: str | int | None = None
    hasNextPage: bool
    perPage: int
    page: int
    searchUrl: str
    stickyItems: list[BaseItem]

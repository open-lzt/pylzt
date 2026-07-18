"""Hand-patched — codegen declared `canResellItemAfterPurchase: bool` (required) and
omitted `bumpSettings` entirely from the OpenAPI spec, but a live category search
(2026-07-05) shows both missing/nullable on many real listings across every category.

Second pass (same date): `isIgnored`, `hasPendingAutoBuy`, `note_text`,
`email_provider`, and (where declared) `sold_items_category_count`/
`restore_items_category_count` are all absent on a meaningful fraction of live
listings — loosened to nullable. `priceWithSellerFee` is `float` (live data includes
fractional prices — `int_from_float` errors on the old `int`). `guarantee` is unified
to the shared `ItemGuarantee` model (was a plain `str` in most categories; live values
are structured objects) — see `item_guarantee.py` for its own hand-patch.


Third pass (same date, after re-running the e2e suite against the second-pass fixes): live data showed `guarantee` itself is absent (not just its sub-fields) on most categories -- loosened to `ItemGuarantee | None = None`.

Fourth pass (category-unique fields, same date): `supercellBrawlers` is a dict keyed
by a numeric-string slot index, each value a full brawler object (`id`, `name`,
`power`, `rank`, `trophies`, nested `skin`/`gadgets`/`gears`/... sub-objects) — not a
`list[str]`. Not modeled exactly (no spec coverage for the nested shape to verify
against) — loosened to `dict[str, dict[str, Any]]`, matching the precedent set for
`cart_get_response.py`'s `items` field (see docs/codegen-runbook.md).

Fifth pass (same date, after re-running the e2e suite against the fourth-pass fix):
`supercellBrawlers` also comes back as `[]` (an empty list, not `{}`) on accounts with
no brawlers unlocked — widened to `dict[str, dict[str, Any]] | list[Any] | None`.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.category_discord_item_seller import CategoryDiscordItemSeller
from pylzt.models.market.item_account_link import ItemAccountLink
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee


class SupercellItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categorysupercell"""

    view_count: int
    is_sticky: int
    item_origin: str
    extended_guarantee: int
    nsb: int
    allow_ask_discount: int
    title_en: str
    description_en: str
    email_type: str
    email_provider: str | None = None
    item_domain: str
    resale_item_origin: str
    supercell_item_id: int
    supercell_id: str
    supercell_arena: str
    supercell_brawler_count: int
    supercell_last_activity: int
    supercell_legendary_brawler_count: int
    supercell_town_hall_level: int
    supercell_builder_hall_level: int
    supercell_builder_hall_cup_count: int
    supercell_phone: int
    supercell_laser_level: int
    supercell_scroll_level: int
    supercell_magic_level: int
    supercell_laser_trophies: int
    supercell_scroll_trophies: int
    supercell_magic_trophies: int
    supercell_laser_victories: int
    supercell_scroll_victories: int
    supercell_magic_victories: int
    supercell_laser_battle_pass: int
    supercell_scroll_battle_pass: int
    supercell_magic_battle_pass: int
    supercell_systems: str
    supercell_king_level: int
    supercell_total_heroes_level: int
    supercell_total_troops_level: int
    supercell_total_spells_level: int
    supercell_total_builder_heroes_level: int
    supercell_total_builder_troops_level: int
    feedback_data: str | None = None
    isIgnored: bool | None = None
    priceWithSellerFee: float
    guarantee: ItemGuarantee | None = None
    canViewLoginData: bool
    canUpdateItemStats: bool
    canReportItem: bool
    canViewEmailLoginData: bool
    showGetEmailCodeButton: bool
    canOpenItem: bool
    canCloseItem: bool
    canEditItem: bool
    canDeleteItem: bool
    canStickItem: bool
    canUnstickItem: bool
    bumpSettings: ItemBumpSettings | None = None
    canBumpItem: bool
    canBuyItem: bool
    rub_price: int
    price_currency: str
    canValidateAccount: bool
    canResellItemAfterPurchase: bool | None = None
    isSmallExf: bool
    supercellBrawlers: dict[str, dict[str, Any]] | list[Any] | None = None
    canViewAccountLink: bool
    accountLinks: list[ItemAccountLink]
    accountLink: str
    emailLoginUrl: str
    canChangePassword: bool
    itemOriginPhrase: str
    tags: list[str]
    note_text: str | None = None
    hasPendingAutoBuy: bool | None = None
    descriptionHtml: str
    descriptionEnHtml: str
    descriptionPlain: str
    descriptionEnPlain: str
    seller: CategoryDiscordItemSeller

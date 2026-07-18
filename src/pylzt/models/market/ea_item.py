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


Third pass (same date, after re-running the e2e suite against the second-pass fixes): re-running against live data showed `guarantee` itself is absent (not just its sub-fields) on most categories — loosened to `ItemGuarantee | None = None`.

Fourth pass (category-unique fields, same date): `ea_games.apex-legends` is absent
entirely for a meaningful fraction of listings (accounts with no Apex Legends
activity) — `apex_legends` loosened to `ItemApexLegends | None = None`. `ea_bans`
elements are ban-detail objects (`{"type": ..., "name": ...}`), not strings —
retyped to `list[dict[str, str]]`.

Fifth pass (same date, after re-running the e2e suite against the fourth-pass
fixes): `ea_bans` entries also carry a `date` key with an epoch `int`, not a `str` —
`list[dict[str, str]]` rejected it; widened to `list[dict[str, Any]]`.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasPath, Field

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.item_account_link import ItemAccountLink
from pylzt.models.market.item_apex_legends import ItemApexLegends
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee
from pylzt.models.market.item_seller import ItemSeller


class EAItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categoryea"""

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
    ea_item_id: int
    ea_id: int
    ea_country: str
    apex_legends: ItemApexLegends | None = Field(
        default=None, validation_alias=AliasPath("ea_games", "apex-legends")
    )
    ea_game_count: int
    ea_last_activity: int
    ea_al_level: int
    ea_al_rank_score: int
    ea_subscription: str
    ea_subscription_end_date: int
    ea_username: str
    ea_xbox_connected: int
    ea_steam_connected: int
    ea_psn_connected: int
    ea_bans: list[dict[str, Any]]
    ea_has_ban: int
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
    canViewAccountLink: bool
    accountLinks: list[ItemAccountLink]
    accountLink: str
    emailLoginUrl: str
    canChangePassword: bool
    itemOriginPhrase: str
    sold_items_category_count: int | None = None
    restore_items_category_count: int | None = None
    tags: list[str]
    note_text: str | None = None
    hasPendingAutoBuy: bool | None = None
    descriptionHtml: str
    descriptionEnHtml: str
    descriptionPlain: str
    descriptionEnPlain: str
    seller: ItemSeller

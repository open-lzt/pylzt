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

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_eg_transaction import ItemEgTransaction
from pylzt.models.market.item_fortnite_past_season import ItemFortnitePastSeason
from pylzt.models.market.item_fortnite_skin import ItemFortniteSkin
from pylzt.models.market.item_guarantee import ItemGuarantee
from pylzt.models.market.item_seller import ItemSeller
from pylzt.models.market.item_shop_counts import ItemShopCounts


class FortniteItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categoryfortnite"""

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
    fortnite_item_id: int
    fortnite_platform: str
    fortnite_register_date: int
    fortnite_last_activity: int
    fortnite_book_level: int
    fortnite_lifetime_wins: int
    fortnite_level: int
    fortnite_season_num: int
    fortnite_books_purchased: int
    fortnite_balance: int
    fortnite_skin_count: int
    fortnite_change_email: int
    fortnite_rl_purchases: int
    fortnite_next_change_email_date: int
    fortnite_last_trans_date: int
    fortnite_xbox_linkable: int
    fortnite_psn_linkable: int
    fortnite_shop_skins_count: int
    fortnite_shop_pickaxes_count: int
    fortnite_shop_dances_count: int
    fortnite_shop_gliders_count: int
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
    fortniteSkins: list[ItemFortniteSkin]
    fortnitePickaxe: list[ItemFortniteSkin]
    fortniteDance: list[ItemFortniteSkin]
    fortniteGliders: list[ItemFortniteSkin]
    fortnite_pickaxe_count: int
    fortnite_dance_count: int
    fortnite_glider_count: int
    fortnitePastSeasons: list[ItemFortnitePastSeason]
    isSmallExf: bool
    account_last_activity: int
    fortniteTransactions: list[ItemEgTransaction]
    domain: str
    shopCounts: ItemShopCounts
    canViewAccountLink: bool
    accountLinks: list[str]
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

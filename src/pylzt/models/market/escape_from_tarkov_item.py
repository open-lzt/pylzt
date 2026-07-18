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

Fourth pass (category-unique fields, same date): `tarkov_deaths`, `tarkov_kills`,
`tarkov_sessions`, `tarkov_mail_forwarding`, and `tarkovKd` are absent on a
meaningful fraction of live listings — loosened to nullable. `tarkov_kd` (a
distinct, lowercase field) comes back as a decimal string (e.g. `"3.50"`), not an
int — retyped to `float` (pydantic coerces the numeric string).

Fifth pass (same date, after re-running the e2e suite against the fourth-pass
fixes): `tarkovSecuredContainer` is also absent on a meaningful fraction of
listings — loosened to nullable.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee
from pylzt.models.market.item_seller import ItemSeller


class EscapeFromTarkovItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categoryescapefromtarkov"""

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
    tarkov_item_id: int
    tarkov_game_version: str
    tarkov_register_date: int
    tarkov_level: int
    tarkov_exp: int
    tarkov_last_activity: int
    tarkov_side: str
    tarkov_rubles: int
    tarkov_secured_container: str
    tarkov_euros: int
    tarkov_dollars: int
    tarkov_kd: float
    tarkov_deaths: int | None = None
    tarkov_kills: int | None = None
    tarkov_sessions: int | None = None
    tarkov_region: str
    tarkov_total_in_game: int
    tarkov_mail_forwarding: int | None = None
    tarkov_username: str
    tarkov_purchase_date: int
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
    tarkovRegionPhrase: str
    tarkovGameVersionPhrase: str
    tarkovSecuredContainer: str | None = None
    tarkovKd: int | None = None
    accountDomain: str
    canViewAccountLink: bool
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

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

Fourth pass (category-unique fields, same date): every `tt_*` field is absent on the
majority of live listings — this isn't a handful of one-off nullables, it's the whole
TikTok-metadata block only populated when a scrape/enrichment step ran for that
listing. All 19 `tt_*` fields batch-loosened to optional (kept flat on this model, not
hoisted into a nested sub-object — there's no live evidence the API itself groups them
under a sub-key; they arrive top-level like everything else on the item).

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.item_account_link import ItemAccountLink
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee
from pylzt.models.market.item_seller import ItemSeller


class TikTokItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categorytiktok"""

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
    tt_item_id: int | None = None
    tt_id: int | None = None
    tt_permalink: str | None = None
    tt_uniqueId: str | None = None
    tt_verified: int | None = None
    tt_createTime: int | None = None
    tt_privateAccount: int | None = None
    tt_followers: int | None = None
    tt_following: int | None = None
    tt_likes: int | None = None
    tt_videos: int | None = None
    tt_screen_name: str | None = None
    tt_hasEmail: int | None = None
    tt_hasMobile: int | None = None
    tt_top_country: str | None = None
    tt_countries: str | None = None
    tt_coins: int | None = None
    tt_hasLivePermission: int | None = None
    tt_cookie_login: int | None = None
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

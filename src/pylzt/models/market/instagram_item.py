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

Fourth pass (category-unique fields, same date): `instagram_id` comes back as a bare
integer on every checked item, not the spec-declared string — widened to `str | int`
(same pattern used for `totalItemsPrice` elsewhere). `emailLoginUrl` is absent on a
meaningful fraction of listings — loosened to nullable.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.category_discord_item_seller import CategoryDiscordItemSeller
from pylzt.models.market.item_account_link import ItemAccountLink
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee


class InstagramItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categoryinstagram"""

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
    instagram_item_id: int
    instagram_id: str | int
    instagram_follower_count: int
    instagram_follow_count: int
    instagram_post_count: int
    instagram_country: str
    instagram_username: str
    instagram_mobile: int
    instagram_register_date: int
    instagram_has_cookies: int
    instagram_login_without_cookies: int
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
    emailLoginUrl: str | None = None
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

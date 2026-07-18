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

Fourth pass (category-unique fields, same date): `emailLoginUrl` is absent on a
meaningful fraction of live listings — loosened to nullable.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.item_account_link import ItemAccountLink
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee
from pylzt.models.market.item_roblox_game_donation import ItemRobloxGameDonation
from pylzt.models.market.item_roblox_game_donations_detail import ItemRobloxGameDonationsDetail
from pylzt.models.market.item_seller import ItemSeller


class RobloxItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categoryroblox"""

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
    roblox_item_id: int
    roblox_id: int
    roblox_email_verified: int
    roblox_robux: int
    roblox_username: str
    roblox_country: str
    roblox_register_date: int
    roblox_friends: int
    roblox_followers: int
    roblox_subscription: str
    roblox_subscription_end_date: int
    roblox_xbox_connected: int
    roblox_incoming_robux_total: int
    roblox_limited_price: int
    roblox_verified: int
    roblox_age_verified: int
    roblox_psn_connected: int
    roblox_subscription_auto_renew: int
    roblox_game_pass_total_robux: int
    roblox_game_donations: str
    roblox_inventory_price: int
    roblox_ugc_limited_price: int
    roblox_credit_balance: int
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
    robloxLinkedAccounts: str
    creditBalance: str
    robloxGameDonations: list[ItemRobloxGameDonation]
    robloxGameDonationsDetails: list[ItemRobloxGameDonationsDetail]
    canViewAccountLink: bool
    accountLinks: list[ItemAccountLink]
    accountLink: str
    emailLoginUrl: str | None = None
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

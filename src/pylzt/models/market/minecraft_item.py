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

Fourth pass (category-unique fields, same date): `minecraft_hypixel_ban` is `None`
on accounts with no Hypixel ban record — loosened to nullable. `minecraft_capes`
elements are `{"name": ...}` objects, not strings — retyped to `list[dict[str, Any]]`.
`emailLoginUrl` is absent on a meaningful fraction of listings — loosened to nullable.

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


class MinecraftItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categoryminecraft"""

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
    minecraft_item_id: int
    minecraft_id: str
    minecraft_nickname: str
    minecraft_country: str
    minecraft_skin: str
    minecraft_java: int
    minecraft_bedrock: int
    minecraft_can_change_nickname: int
    minecraft_created_at: int
    minecraft_hypixel_rank: str
    minecraft_hypixel_level: int
    minecraft_hypixel_achievement: int
    minecraft_hypixel_last_login: int
    minecraft_hypixel_ban: int | None = None
    minecraft_hypixel_ban_reason: str
    minecraft_hypixel_skyblock_level: int
    minecraft_hypixel_skyblock_net_worth: int
    minecraft_dungeons: int
    minecraft_legends: int
    minecraft_capes_count: int
    minecraft_capes: list[dict[str, Any]]
    minecraft_subscription_name: str
    minecraft_subscription_ends: int
    minecraft_subscription_auto_renew: int
    minecraft_email_reset_date: int
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
    minecraftHasPaidLicense: bool
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

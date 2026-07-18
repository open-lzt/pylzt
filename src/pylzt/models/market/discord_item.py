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

Fourth pass (same date): `discord_nitro_type` is `"none"` on live listings, not an int — the
spec's `int` was wrong outright, not just missing/nullable. Only one literal value has been
observed so far, not enough to pin a `StrEnum` domain confidently — retyped to `str | None`
until more values are seen live.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.category_discord_item_seller import CategoryDiscordItemSeller
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee


class DiscordItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categorydiscord"""

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
    discord_item_id: int
    discord_chat_count: int
    discord_verified: int
    discord_condition: str
    discord_gifts: int
    discord_billing: int
    discord_register_date: int
    discord_locale: str
    discord_nitro_end_date: int
    discord_available_boosts: int
    discord_nitro_type: str | None = None
    discord_admin_members_count: int
    discord_admin_servers_count: int
    discord_admin_servers: str
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
    discordAccountConditionLabel: str
    discordLocaleTitle: str
    discordNitroType: str
    canViewAccountLink: bool
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

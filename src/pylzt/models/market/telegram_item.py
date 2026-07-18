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

Fourth pass (category-unique fields, same date): `telegram_spam_block` comes back as
a plain int (e.g. `-1`) on most listings, not the spec-declared string — retyped to
`int | None`.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.category_discord_item_seller import CategoryDiscordItemSeller
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee
from pylzt.models.market.item_telegram_group_counters import ItemTelegramGroupCounters


class TelegramItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categorytelegram"""

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
    telegram_item_id: int
    telegram_country: str
    telegram_last_seen: int
    telegram_premium: int
    telegram_stars_count: int
    telegram_birthday: int
    telegram_password: int
    telegram_premium_expires: int
    telegram_spam_block: int | None = None
    telegram_channels_count: int
    telegram_chats_count: int
    telegram_admin_count: int
    telegram_admin_subs_count: int
    telegram_conversations_count: int
    telegram_id_count: int
    telegram_contacts_count: int
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
    telegram_group_counters: ItemTelegramGroupCounters
    canViewAccountLink: bool
    accountLinks: list[str]
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

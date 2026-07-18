"""Hand-patched — a live category search (2026-07-05) shows `isIgnored`,
`hasPendingAutoBuy`, `note_text`, and `email_provider` all absent on a meaningful
fraction of live listings — loosened to nullable. `guarantee` is unified to the
shared `ItemGuarantee` model (was a plain `str` — live values are structured objects) —
see `item_guarantee.py` for its own hand-patch. `priceWithSellerFee` was already
`float` here (correct).
Third pass (same date, after re-running the e2e suite against the second-pass fixes): re-running against live data showed `guarantee` itself is absent (not just its sub-fields) on most categories — loosened to `ItemGuarantee | None = None`.

Fourth pass (category-unique fields, same date): `buyer` and `public_tag` come back
`None` on unsold / untagged listings — loosened to nullable.

Promoting this out of codegen intentionally clashes with the
next `dev.codegen build --api market` (`_guard_no_clobber`) — see
docs/codegen-runbook.md.
"""

from __future__ import annotations

from pydantic import AliasPath, Field

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.category_discord_item_seller import CategoryDiscordItemSeller
from pylzt.models.market.item_category import ItemCategory
from pylzt.models.market.item_guarantee import ItemGuarantee


class HytaleItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categoryhytale"""

    pending_deletion_date: int
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
    auto_bump_period: int
    rub_price: int
    discount: bool
    hytale_item_id: int
    hytale_profiles: int
    hytale_edition: str
    feedback_data: str | None = None
    max_discount_percent: int
    isIgnored: bool | None = None
    priceWithSellerFee: float
    category: ItemCategory
    guarantee: ItemGuarantee | None = None
    canViewLoginData: bool
    canViewTempEmail: bool
    canUpdateItemStats: bool
    canReportItem: bool
    canViewItemViews: bool
    canManagePublicTag: bool
    canViewEmailLoginData: bool
    title_link: str = Field(validation_alias=AliasPath("copyFormatData", "title_link"))
    showGetEmailCodeButton: bool
    canOpenItem: bool
    canCloseItem: bool
    canEditItem: bool
    canDeleteItem: bool
    canStickItem: bool
    canUnstickItem: bool
    canBumpItem: bool
    canNotBumpItemReason: str
    buyer: str | None = None
    isPersonalAccount: bool
    canBuyItem: bool
    price_currency: str
    priceWithSellerFeeLabel: str
    canValidateAccount: bool
    canResellItem: bool
    canViewAccountLink: bool
    imagePreviewLinks: list[str]
    emailLoginUrl: str
    canChangePassword: bool
    canChangeEmailPassword: bool
    uniqueKeyExists: bool
    itemOriginPhrase: str
    tags: list[str]
    public_tag: str | None = None
    note_text: str | None = None
    hasPendingAutoBuy: bool | None = None
    descriptionHtml: str
    descriptionEnHtml: str
    descriptionPlain: str
    descriptionEnPlain: str
    seller: CategoryDiscordItemSeller

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

Fourth pass (same date): `eg_games` values (`ItemEgGame`) legitimately omit `category_id`/
`ru`/`hits_count` on live data — loosened in `item_eg_game.py`. Live data also shows at
least one listing where `eg_games` itself isn't a map (empty list instead) — loosened the
field to accept that shape too.

Fifth pass (same date, full-suite re-run against a shifted live listings page):
`eg_code_redemption_history` elements are full redemption-event objects (`description`,
`redeemedDate`, `friendlyCode`), not plain strings — loosened to `list[dict[str, Any]]`
(same "not modeled exactly" precedent as `r6Skins`/`cart_get_response.py`'s `items`).

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_eg_game import ItemEgGame
from pylzt.models.market.item_eg_transaction import ItemEgTransaction
from pylzt.models.market.item_guarantee import ItemGuarantee
from pylzt.models.market.item_seller import ItemSeller


class EpicGamesItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categoryepicgames"""

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
    eg_item_id: int
    eg_country: str
    eg_code_redemption_history: list[dict[str, Any]]
    eg_coupons: list[str]
    eg_games: dict[str, ItemEgGame] | list[Any] | None = None
    eg_change_email: int
    eg_can_update_display_name: int
    eg_last_activity: int
    eg_payment_methods: list[str]
    eg_rl_purchases: int
    eg_username: str
    eg_rewards_balance: int
    eg_rewards_expiration_date: int
    eg_next_change_email_date: int
    eg_game_count: int
    eg_balance: int
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
    egBalance: str
    egGameCount: int
    egTransactions: list[ItemEgTransaction]
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

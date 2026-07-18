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

Fourth pass (same date, re-running the e2e suite live): `uplay_r6_skins`, `uplay_steam_connected`,
`uplayR6Rank`, and `account_last_activity` are all still absent on a meaningful fraction of
live listings -- loosened to nullable. `uplay_games` values legitimately omit
`pvpTimePlayed`/`pveTimePlayed` -- see `item_uplay_game.py` for its own hand-patch.
`r6Skins` elements are full Ubisoft store-item objects (`item_id`, `name`, `display_name`,
`image`, `type`, `data` as a nested JSON string, `viewer.meta.{...}`), not plain strings --
loosened to `list[dict[str, Any]]` (same "not modeled exactly" precedent as
`cart_get_response.py`'s `items` and `forum.py`'s `forum_moderators`).

Fifth pass (same date, full-suite re-run): `uplay_games` itself is sometimes a `list[dict]`
of game objects (title/id) instead of the `dict[str, ItemUplayGame]` map -- same
alt-empty-shape pattern as `eg_games`/`socialclub_games` elsewhere in this file family --
widened to `dict[str, ItemUplayGame] | list[Any] | None`.

Sixth pass (2026-07-08, e2e re-run against a live CategoryUplay search): `emailLoginUrl`
absent on a real listing (item #21 of that page) -- loosened to `str | None = None`.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee
from pylzt.models.market.item_r6_operator import ItemR6Operator
from pylzt.models.market.item_seller import ItemSeller
from pylzt.models.market.item_uplay_game import ItemUplayGame


class UplayItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categoryuplay"""

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
    uplay_item_id: int
    uplay_last_activity: int
    uplay_country: str
    uplay_created_date: int
    uplay_games: dict[str, ItemUplayGame] | list[Any] | None = None
    uplay_game_count: int
    uplay_r6_level: int
    uplay_r6_ban: int
    uplay_r6_operators: str
    uplay_r6_operators_count: int
    uplay_r6_skins: str | None = None
    uplay_r6_skins_count: int
    uplay_subscription: str
    uplay_subscription_end_date: int
    uplay_xbox_connected: int
    uplay_psn_connected: int
    uplay_steam_connected: int | None = None
    uplay_r6_rank: int
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
    uplayLinkedAccounts: str
    uplayR6Rank: str | None = None
    uplay_r6_steam_warning: bool
    uplay_r6_external_warning: bool
    uplay_r6: bool
    uplay_r6_ban_active: bool
    isSmallExf: bool
    account_last_activity: int | None = None
    r6Skins: list[dict[str, Any]]
    r6Operators: list[ItemR6Operator]
    canViewAccountLink: bool
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

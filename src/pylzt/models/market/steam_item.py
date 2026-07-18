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

Fourth pass (category-unique fields, same date): the nine `steam_*_inv_value` fields
are `None` on accounts with no owned inventory for that game (not a float/string as
guessed pre-verification — a live check via `exc.errors(include_input=True)` showed
`input=None` on every failing item), loosened to `int | None`. `steam_faceit_level`,
`dota2CalibrationWarning`, `cs2RankExpired`, `steamDota2WinRate` are simply absent on
most listings — loosened to optional. `steam_bans` is a `dict[str, str]` (Steam appid
-> ban reason, e.g. `{"730": "CS2 Prime"}`), not a `str` — see `item_steam_full_games.py`
for the matching `steam_full_games.list` fix (empty-inventory case returns `[]`).

Fifth pass (same date, re-running against the fourth-pass fixes): `steam_bans` also
comes back as `""` (an empty string, not `{}`) when the account has no bans — a
`before` validator now maps that to `None` instead of failing `dict_type`.

Sixth pass (category-unique fields, same date): `inventoryValue` — a distinct field
from the `steam_*_inv_value` fields above — is a list of per-game summary objects
(`{"title": ..., "value": ..., "field": ...}`), not strings — retyped its elements
to `dict[str, Any]`.

Seventh pass (same date, after re-running the e2e suite against the sixth-pass
fixes — a live listing sample can vary run to run, so this surfaced only once
enough accounts with populated cs2/medal data showed up): `steamCs2Medals` and
`cs2MapsRanks` are also lists of structured objects (medal title/icon, per-map
rank), not strings — retyped both to `list[dict[str, Any]]`.

Eighth pass (same date, after re-running the e2e suite against the seventh-pass
fixes): `cs2PremierElo` comes back as a single rank-progress object
(`{"big": ..., "small": ..., "brand": ...}`) rather than the spec-declared list on
at least one account — widened to `list[str] | dict[str, Any]`.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasPath, Field, field_validator

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.item_account_link import ItemAccountLink
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee
from pylzt.models.market.item_seller import ItemSeller
from pylzt.models.market.item_steam_full_games import ItemSteamFullGames
from pylzt.models.market.item_steam_transaction import ItemSteamTransaction


class SteamItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categorysteam"""

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
    steam_item_id: int
    steam_country: str
    steam_register_date: int
    steam_last_activity: int
    steam_full_games: ItemSteamFullGames
    steam_community_ban: int
    steam_bans: dict[str, str] | None = None
    steam_cs2_profile_rank: int
    steam_balance: str
    steam_cs2_rank_id: int
    steam_is_limited: int
    steam_level: int
    steam_friend_count: int
    steam_cs2_last_activity: int
    steam_dota2_solo_mmr: int
    steam_cs2_ban_date: int
    steam_converted_balance: int
    steam_cards_count: int
    steam_cards_games: int
    steam_pubg_inv_value: int | None = None
    steam_cs2_inv_value: int | None = None
    steam_dota2_inv_value: int | None = None
    steam_tf2_inv_value: int | None = None
    steam_rust_inv_value: int | None = None
    steam_cs2_wingman_rank_id: int
    steam_game_count: int
    steam_steam_inv_value: int | None = None
    steam_inv_value: int
    steam_cs2_win_count: int
    steam_dota2_game_count: int
    steam_dota2_lose_count: int
    steam_dota2_win_count: int
    steam_hours_played_recently: str
    steam_faceit_level: int | None = None
    steam_points: int
    steam_last_transaction_date: int
    steam_relevant_game_count: int
    steam_gift_count: int
    steam_limit_spent: str
    steam_dota2_behavior: int
    steam_mfa: int
    steam_market: int
    steam_market_restrictions: int
    steam_market_ban_end_date: int
    steam_unturned_inv_value: int | None = None
    steam_cs2_last_launched: int
    steam_kf2_inv_value: int | None = None
    steam_dst_inv_value: int | None = None
    steam_cs2_premier_elo: int
    steam_has_activated_keys: int
    steam_cs2_ban_type: int
    steam_rust_kill_player: int
    steam_rust_deaths: int
    steam_total_gifts_rub: int
    steam_total_refunds_rub: int
    steam_total_ingame_rub: int
    steam_total_games_rub: int
    steam_total_purchased_rub: int
    steam_dota2_last_match_date: int
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
    steam_ban_type_id: list[str] = Field(
        validation_alias=AliasPath("steamData", "steam_ban_type_id")
    )
    steamRelevantGameCount: int
    isSmallExf: bool
    account_last_activity: int
    hasCs2: bool
    hasDota2: bool
    hasPubg: bool
    hasTf2: bool
    hasRust: bool
    steam_cs2_ban_date_active: bool
    dota2CalibrationWarning: bool | None = None
    displayConvertedBalance: bool
    inventoryValue: list[dict[str, Any]]
    steamCs2Medals: list[dict[str, Any]]
    cs2RankExpired: bool | None = None
    steamDota2WinRate: int | None = None
    steamTransactions: list[ItemSteamTransaction]
    hasPossibleBanInDota2: bool
    chineseAccount: bool
    cs2MapsRanks: list[dict[str, Any]]
    cs2PremierElo: list[str] | dict[str, Any]
    steamLifetimeTradeBan: bool
    canViewAccountLink: bool
    accountLinks: list[ItemAccountLink]
    accountLink: str
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

    @field_validator("steam_bans", mode="before")
    @classmethod
    def _empty_string_bans_to_none(cls, value: object) -> object:
        return None if value == "" else value

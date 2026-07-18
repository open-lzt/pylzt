"""Hand-patched — a live category search (2026-07-05) shows `isIgnored`,
`hasPendingAutoBuy`, `note_text`, `email_provider`, `sold_items_category_count`, and
`restore_items_category_count` all absent on a meaningful fraction of live listings —
loosened to nullable. `priceWithSellerFee` is `float` (live data includes fractional
prices — `int_from_float` errors on the old `int`). `guarantee` is unified to the
shared `ItemGuarantee` model (was a plain `str` — live values are structured objects) —
see `item_guarantee.py` for its own hand-patch.
Third pass (same date, after re-running the e2e suite against the second-pass fixes): live data showed `guarantee` itself is absent (not just its sub-fields) on most categories -- loosened to `ItemGuarantee | None = None`.

Fourth pass (category-unique fields, same date): `bumpSettings`/`canResellItemAfterPurchase`
were declared required here even though the same two fields were batch-loosened across the
other 18 category item models in an earlier pass — this file was missed by that batch (it
still carried the auto-gen header at the time, unlike the other 18 which had already been
promoted to hand-patched), not a per-category exception; loosened to match. `riot_valorant_knife`,
`valorantRegionPhrase`, `valorantRankTitle`, `valorantRankImgPath`, `valorantPreviousRankTitle`,
`valorantLastRankTitle` are absent on a meaningful fraction of live listings — loosened to
optional. `valorantInventory`/`lolInventory` are `[]` (not a dict) on accounts with no
inventory for that game — loosened to accept `ItemValorantInventory | ItemLolInventory | list[Any] | None`.
`ItemLolInventory.Skin` is a slot-index -> skin-id map (`dict[str, int]`), not a list — see
`item_lol_inventory.py` for its own hand-patch (`Champion` stays `list[int]`: no live listing
failed on it).

Fifth pass (category-unique fields, same date, re-running against the fourth-pass
fixes): `lolRegionPhrase` and `emailLoginUrl` are absent on a meaningful fraction of
listings — loosened to optional. `valorantInventory`'s `WeaponSkins` still failed on
one item even after the parent field was widened — the real value there is a
slot-index -> skin-id map (`dict[str, str]`), not a list; see
`item_valorant_inventory.py` for its own hand-patch widening `WeaponSkins` itself.
`feedback_data` (a field declared identically across every category item model, not
riot-specific) is `None` on a small fraction of listings — loosened to optional here;
the other 18 category models likely carry the same required-`str` bug and should be
audited in a follow-up pass, not fixed blind in this one.

Promoting this out of codegen
intentionally clashes with the next `dev.codegen build --api market`
(`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.item_account_link import ItemAccountLink
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee
from pylzt.models.market.item_lol_inventory import ItemLolInventory
from pylzt.models.market.item_seller import ItemSeller
from pylzt.models.market.item_valorant_inventory import ItemValorantInventory


class RiotItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categoryriot"""

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
    riot_item_id: int
    riot_id: str
    riot_account_verified: int
    riot_email_verified: int
    riot_country: str
    riot_password_change: int
    riot_phone_verified: int
    riot_last_activity: int
    riot_valorant_wallet_vp: int
    riot_valorant_wallet_rp: int
    riot_valorant_wallet_fa: int
    riot_valorant_level: int
    riot_username: str
    riot_valorant_rank: int
    riot_valorant_region: str
    riot_valorant_skin_count: int
    riot_valorant_agent_count: int
    riot_valorant_previous_rank: int
    riot_valorant_last_rank: int
    riot_valorant_rank_type: str
    riot_valorant_inventory_value: int
    riot_valorant_knife: int | None = None
    riot_lol_region: str
    riot_lol_skin_count: int
    riot_lol_champion_count: int
    riot_lol_level: int
    riot_lol_wallet_blue: int
    riot_lol_wallet_orange: int
    riot_lol_wallet_mythic: int
    riot_lol_wallet_riot: int
    riot_lol_rank: str
    riot_lol_rank_win_rate: int
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
    valorantRegionPhrase: str | None = None
    valorantRankTitle: str | None = None
    valorantRankImgPath: str | None = None
    valorantPreviousRankTitle: str | None = None
    valorantLastRankTitle: str | None = None
    lolRegionPhrase: str | None = None
    isSmallExf: bool
    account_last_activity: int
    valorantInventory: ItemValorantInventory | list[Any] | None = None
    lolInventory: ItemLolInventory | list[Any] | None = None
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

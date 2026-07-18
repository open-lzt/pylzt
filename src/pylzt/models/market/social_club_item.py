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

Fourth pass (category-unique fields, same date): `socialclub_games` comes back as a
JSON-encoded string of game slugs (e.g. `'["gta5","bully",...]'`), not a list of
`ItemSocialclubGame` objects — that spec-declared rich-object shape was never observed
live. Retyped to `list[str] | None` with a `before` validator that `json.loads`s the
wire string (falls back to `None` on anything that isn't a JSON array of strings,
rather than raising, since this is a display field, not one anything transacts on).
`socialclub_has_gtav`/`socialclub_has_rdr2` are absent whenever the account has no
data for that specific game — loosened to optional.

Fifth pass (category-unique fields, same date): `account_last_activity` is absent
on a meaningful fraction of listings — loosened to optional.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

import json

from pydantic import field_validator

from pylzt.models.market.base_item import BaseItem
from pylzt.models.market.category_discord_item_seller import CategoryDiscordItemSeller
from pylzt.models.market.item_bump_settings import ItemBumpSettings
from pylzt.models.market.item_guarantee import ItemGuarantee


class SocialClubItem(BaseItem):
    """Docs: https://lzt-market.readme.io/reference/categorysocialclub"""

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
    socialclub_item_id: int
    socialclub_level: int
    socialclub_cash: int
    socialclub_bank_cash: int
    socialclub_games: list[str] | None = None
    socialclub_last_activity: int
    socialclub_has_gtav: int | None = None
    socialclub_has_rdr2: int | None = None
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
    isSmallExf: bool
    account_last_activity: int | None = None
    canViewAccountLink: bool
    accountLinks: list[str]
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

    @field_validator("socialclub_games", mode="before")
    @classmethod
    def _parse_socialclub_games(cls, value: object) -> list[str] | None:
        if value is None or isinstance(value, list):
            return value
        if not isinstance(value, str):
            return None
        try:
            parsed = json.loads(value)
        except ValueError:
            return None
        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
            return parsed
        return None

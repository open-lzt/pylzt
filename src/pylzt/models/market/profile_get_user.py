"""Hand-patched — a live `/profile/get` capture (2026-07-05) shows several spec
mismatches. `balances` is absent entirely for this account (no linked payout balances
configured). `convertedBalance` is a `float` (`1451.94`), not the spec's `int` — matches
the `priceWithSellerFee` fix pattern used elsewhere. `feedback_data`/`restore_data` are
`None`/`[]` in practice, not always the spec's `dict`. `rendered.backgrounds` and
`telegram_client` are `[]` in practice instead of their modeled shape (loosened at
`user_rendered.py` / here respectively). `imap_data` is not a fixed `{"domain.zone": ...}`
key the codegen `AliasPath` hack assumed — it's a dynamic map keyed by the real IMAP
domain (`podli.online`, `aeromailis.online`, ...), same pattern as `eg_games` — replaced
the `domain_zone`/`AliasPath` field with a direct `imap_data` map — see
docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pylzt.models.base import LolzObject
from pylzt.models.market.item_public_tag import ItemPublicTag
from pylzt.models.market.tag import Tag
from pylzt.models.market.user_balance import UserBalance
from pylzt.models.market.user_custom_fields import UserCustomFields
from pylzt.models.market.user_dob import UserDob
from pylzt.models.market.user_domain_zone import UserDomainZone
from pylzt.models.market.user_rendered import UserRendered
from pylzt.models.market.user_telegram_client import UserTelegramClient


class ProfileGetUser(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/profileget"""

    active_items_count: int
    activity_visible: bool
    age: int
    balance: str
    balances: list[UserBalance] | None = None
    bump_item_period: int
    can_edit: bool
    can_follow: bool
    can_ignore: bool
    can_post_profile: bool
    can_view_profile: bool
    can_view_profile_posts: bool
    can_warn: bool
    contest_count: int
    conv_welcome_message: str
    convertedBalance: float
    convertedDeposit: int
    convertedHold: int
    currency: str
    currencyPhrase: str
    custom_account_download_format: str
    custom_fields: UserCustomFields
    custom_title: str
    deposit: int
    dob: UserDob
    feedback_data: dict[str, Any] | list[Any] | None = None
    hold: str
    homepage: str
    imap_data: dict[str, UserDomainZone] | None = None
    is_admin: bool
    is_banned: bool
    is_followed: bool
    is_ignored: bool
    is_moderator: bool
    is_staff: bool
    is_super_admin: bool
    joined_date: int
    last_activity: int
    like2_count: int
    like_count: int
    location: str
    market_custom_title: str
    max_discount_percent: int
    message_count: int
    paid_mail_left: int
    public_tags: list[ItemPublicTag]
    register_date: int
    rendered: UserRendered
    restore_count: int
    restore_data: dict[str, Any] | list[Any] | None = None
    short_link: str
    sold_items_count: int
    tags: list[Tag]
    telegram_client: UserTelegramClient | list[Any] | None = None
    trophy_points: int
    user_allow_ask_discount: bool
    user_id: int
    user_title: str
    username: str
    view_url: str
    visible: bool
    warning_points: int

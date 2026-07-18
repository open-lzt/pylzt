"""Opaque ids and closed enums shared across the SDK.

Ids are `NewType` over `int`/`str` so they never silently mix at call sites
(an `ItemId` is not interchangeable with a `TokenId`) while staying zero-cost at
runtime. Domain enums are `StrEnum` with an `OTHER` fallback where the upstream
vocabulary is open-ended (`item_origin`, `category`), so an unknown literal from
the API degrades gracefully instead of crashing the parse.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NewType

ItemId = NewType("ItemId", int)
TokenId = NewType("TokenId", str)
ProxyId = NewType("ProxyId", str)
SellerId = NewType("SellerId", int)


class RateClass(StrEnum):
    """Rate-limit class a request declares; the token pool meters each separately.

    Official published ceilings (confirmed 2026-07-04): `general` = 120 req/min
    (0.5 s spacing) and `search` = 20 req/min (Category Search, 3 s spacing) on
    Market; `forum` = 300 req/min (0.2 s spacing) on the Forum API.
    """

    GENERAL = "general"
    SEARCH = "search"
    FORUM = "forum"
    ANTIPUBLIC = "antipublic"


class ApiTarget(StrEnum):
    """Which host a `BaseMethod` talks to — `Client` routes to the matching transport.

    `market` = `prod-api.lzt.market`; `forum` = `prod-api.lolz.live` (verified live
    2026-07-03; see `ClientConfig.base_url`/`forum_base_url`). `antipublic` =
    `antipublic.one/api/v2`, a separate leak-checking API with its own Bearer license
    key (never merged into the market/forum token pool — see `token_pool/_static.py`).
    """

    MARKET = "market"
    FORUM = "forum"
    ANTIPUBLIC = "antipublic"


class HttpMethod(StrEnum):
    """Wire verb a method-class declares. The market API adds PUT/DELETE over the web
    surface (per the official reference); the read core only ever needs GET/POST."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class ProxyScheme(StrEnum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class ProxyOutcome(StrEnum):
    """Result of a request through a proxy, fed back to the per-proxy breaker."""

    OK = "ok"
    TIMEOUT = "timeout"
    BANNED = "banned"
    CONN_FAIL = "conn_fail"


class OrderBy(StrEnum):
    PRICE_ASC = "price_to_up"
    PRICE_DESC = "price_to_down"
    NEWEST = "pdate_to_down_upload"
    OLDEST = "pdate_to_up_upload"


class Category(StrEnum):
    """Market category slug. Open-ended upstream — unknowns map to `OTHER`."""

    STEAM = "steam"
    DISCORD = "discord"
    FORTNITE = "fortnite"
    TELEGRAM = "telegram"
    RIOT = "riot"
    ROBLOX = "roblox"
    EPICGAMES = "epicgames"
    BATTLENET = "battlenet"
    EA = "ea"
    ESCAPEFROMTARKOV = "escapefromtarkov"
    GIFTS = "gifts"
    INSTAGRAM = "instagram"
    MINECRAFT = "minecraft"
    MIHOYO = "mihoyo"
    SOCIALCLUB = "socialclub"
    SUPERCELL = "supercell"
    TIKTOK = "tiktok"
    UPLAY = "uplay"
    VPN = "vpn"
    WARFACE = "warface"
    WOT = "wot"
    WOTBLITZ = "wotblitz"
    HYTALE = "hytale"
    LLM = "llm"
    VK = "vkontakte"
    OTHER = "other"

    @classmethod
    def parse(cls, value: str) -> Category:
        """Map a raw slug to a member, falling back to `OTHER` for unknowns."""
        try:
            return cls(value)
        except ValueError:
            return cls.OTHER


class ItemOrigin(StrEnum):
    """How the account was obtained. Open-ended upstream — unknowns map to `OTHER`."""

    BRUTE = "brute"
    FISHING = "fishing"
    AUTOREG = "autoreg"
    RESALE = "resale"
    SELF_REGISTRATION = "self_registration"
    DUMP = "dump"
    OTHER = "other"

    @classmethod
    def parse(cls, value: str) -> ItemOrigin:
        try:
            return cls(value)
        except ValueError:
            return cls.OTHER


class Currency(StrEnum):
    CNY = "cny"
    USD = "usd"
    RUB = "rub"
    EUR = "eur"
    UAH = "uah"
    KZT = "kzt"
    BYN = "byn"
    GBP = "gbp"
    # Confirmed live by AS7RIDENIED/LOLZTEAM's own Market.Currency enum (2026-07-08) — our
    # OpenAPI spec doesn't enumerate every currency the market actually prices lots in, and
    # `.parse()`'s fallback silently mapped any of these four to RUB before this addition.
    PLN = "pln"
    TRY = "try"
    JPY = "jpy"
    BRL = "brl"

    @classmethod
    def parse(cls, value: str) -> Currency:
        try:
            return cls(value.lower())
        except ValueError:
            return cls.RUB


class Tristate(StrEnum):
    """Generic yes/no/nomatter filter value. The OpenAPI spec models dozens of unrelated
    params (`tel`, `editBtag`, `clashPass`, `spam`, ...) with this exact wire vocabulary
    under a different name each time; codegen reuses this one class for all of them
    instead of emitting a per-field duplicate (see `_enum_from_schema` in dev/codegen)."""

    YES = "yes"
    NO = "no"
    NOMATTER = "nomatter"

    @classmethod
    def from_bool(cls, value: bool | None) -> Tristate:
        """`None` (don't filter) -> NOMATTER, else YES/NO."""
        if value is None:
            return cls.NOMATTER
        return cls.YES if value else cls.NO

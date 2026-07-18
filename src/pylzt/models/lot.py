"""Market lot — the immutable domain view of a single lzt.market listing.

`Lot` is the parsed, typed shape every layer above the transport consumes; the
raw wire dict never escapes `Lot.from_raw`. `content_hash` is a stable digest
over the price-relevant fields only, so a pure metadata refresh (view_count,
refreshed_date) does not look like a changed listing to a dedup/diff consumer.
`extra="ignore"` semantics: unknown wire keys are dropped, so an upstream field
addition never breaks parsing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from pylzt.models.base import BoundModel
from pylzt.types import Category, Currency, ItemId, ItemOrigin, OrderBy, SellerId

_ATTR_KEYS = ("description", "information")


def _content_hash(
    price: Decimal,
    title: str,
    item_origin: ItemOrigin,
    guarantee: str,
    nsb: bool,
    item_state: str,
) -> str:
    payload = repr((str(price), title, item_origin.value, guarantee, nsb, item_state))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Lot(BaseModel, BoundModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    item_id: ItemId
    category: Category
    price: Decimal
    currency: Currency
    title: str
    seller_id: SellerId
    published_at: datetime
    item_state: str
    item_origin: ItemOrigin
    guarantee: str
    nsb: bool
    content_hash: str
    attributes: Mapping[str, str]

    _UNHASHED_FIELDS: ClassVar[frozenset[str]] = frozenset({"attributes"})

    def __hash__(self) -> int:
        # `attributes` (a Mapping) is deliberately excluded — same reasoning as the old
        # dataclass's `field(hash=False)`: it's descriptive metadata, not part of a lot's
        # identity, and Mapping/MappingProxyType aren't hashable anyway. Derived from
        # `model_fields` (minus the exclusion) rather than a hand-listed tuple, so a future
        # field addition is covered automatically instead of needing a matching edit here.
        return hash(
            tuple(
                getattr(self, name)
                for name in type(self).model_fields
                if name not in self._UNHASHED_FIELDS
            )
        )

    async def refresh(self) -> Lot:
        """Re-fetch this lot from the market through the bound client (returns a fresh `Lot`)."""
        return await self.client.market.get_lot(self.item_id)

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> Lot:
        price = Decimal(str(raw.get("price", 0)))
        title = str(raw.get("title", ""))
        item_state = str(raw.get("item_state", ""))
        item_origin = ItemOrigin.parse(str(raw.get("item_origin", "")))
        guarantee = str(raw.get("guarantee", ""))
        nsb = bool(raw.get("nsb", False))

        seller = raw.get("seller")
        seller_uid = int(seller.get("user_id", 0) or 0) if isinstance(seller, Mapping) else 0

        try:
            published_at = datetime.fromtimestamp(float(raw.get("published_date", 0) or 0), tz=UTC)
        except (TypeError, ValueError, OSError, OverflowError):
            published_at = datetime.fromtimestamp(0, tz=UTC)

        currency_raw = raw.get("price_currency") or raw.get("currency") or ""
        attributes = MappingProxyType(
            {k: str(raw[k]) for k in _ATTR_KEYS if raw.get(k) is not None}
        )

        return cls(
            item_id=ItemId(int(raw.get("item_id", 0) or 0)),
            category=Category.parse(str(raw.get("category", ""))),
            price=price,
            currency=Currency.parse(str(currency_raw)),
            title=title,
            seller_id=SellerId(seller_uid),
            published_at=published_at,
            item_state=item_state,
            item_origin=item_origin,
            guarantee=guarantee,
            nsb=nsb,
            content_hash=_content_hash(price, title, item_origin, guarantee, nsb, item_state),
            attributes=attributes,
        )

    @classmethod
    def from_raw_many(cls, envelope: Mapping[str, Any]) -> list[Lot]:
        items = envelope.get("items", [])
        if isinstance(items, Mapping):
            raws: list[Any] = list(items.values())
        elif isinstance(items, list):
            raws = items
        else:
            raws = []
        return [cls.from_raw(raw) for raw in raws if isinstance(raw, Mapping)]


class LotFilter(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: Category | None = None
    pmin: Decimal | None = None
    pmax: Decimal | None = None
    title: str | None = None
    game: tuple[str, ...] = ()
    order_by: OrderBy | None = None

    def to_query(self) -> dict[str, Any]:
        """Render the lzt.market query params; `category` is a path part, not a param."""
        params: dict[str, Any] = {}
        if self.pmin is not None:
            params["pmin"] = str(self.pmin)
        if self.pmax is not None:
            params["pmax"] = str(self.pmax)
        if self.title is not None:
            params["title"] = self.title
        if self.order_by is not None:
            params["order_by"] = self.order_by.value
        if self.game:
            # Wire key is "games" (plural) — verified live 2026-07-04: "game[]=" silently
            # matches 0 lots, "games[]=" is the real param the search endpoint reads.
            params["games"] = list(self.game)
        return params

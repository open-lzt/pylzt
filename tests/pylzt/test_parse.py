from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pylzt.models.lot import Lot
from pylzt.types import Category, Currency, ItemOrigin


def _raw(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "item_id": 12345,
        "category": "steam",
        "price": 1500,
        "price_currency": "rub",
        "title": "Steam account",
        "item_state": "active",
        "item_origin": "brute",
        "guarantee": "12 hours",
        "nsb": True,
        "published_date": 1700000000,
        "view_count": 10,
        "refreshed_date": 1700001000,
        "description": "desc",
        "information": "info",
        "seller": {"user_id": 999, "username": "bob"},
        "totally_unknown_field": "ignored",
    }
    base.update(over)
    return base


def test_from_raw_typed_fields() -> None:
    lot = Lot.from_raw(_raw())
    assert isinstance(lot.price, Decimal)
    assert lot.price == Decimal("1500")
    assert lot.currency is Currency.RUB
    assert lot.category is Category.STEAM
    assert lot.item_origin is ItemOrigin.BRUTE
    assert lot.seller_id == 999
    assert lot.nsb is True
    assert lot.item_id == 12345


def test_published_at_is_tz_aware_utc() -> None:
    lot = Lot.from_raw(_raw())
    assert lot.published_at.tzinfo is UTC
    assert lot.published_at == datetime.fromtimestamp(1700000000, tz=UTC)


def test_unknown_fields_ignored() -> None:
    lot = Lot.from_raw(_raw(another_unknown=[1, 2, 3]))
    assert lot.item_id == 12345
    assert "description" in lot.attributes
    assert "totally_unknown_field" not in lot.attributes


def test_content_hash_excludes_volatile_fields() -> None:
    a = Lot.from_raw(_raw(view_count=10, refreshed_date=1, update_stat_date=1))
    b = Lot.from_raw(_raw(view_count=99999, refreshed_date=2, update_stat_date=2))
    assert a.content_hash == b.content_hash


def test_content_hash_changes_on_price() -> None:
    a = Lot.from_raw(_raw(price=1500))
    b = Lot.from_raw(_raw(price=1600))
    assert a.content_hash != b.content_hash


def test_from_raw_many_list_form() -> None:
    env = {
        "items": [_raw(item_id=1), _raw(item_id=2)],
        "totalItems": 2,
        "perPage": 50,
        "page": 1,
    }
    lots = Lot.from_raw_many(env)
    assert [lot.item_id for lot in lots] == [1, 2]


def test_from_raw_many_dict_keyed_form() -> None:
    env = {
        "items": {"1": _raw(item_id=1), "2": _raw(item_id=2)},
        "totalItems": 2,
    }
    lots = Lot.from_raw_many(env)
    assert {lot.item_id for lot in lots} == {1, 2}


def test_from_raw_many_empty_envelope() -> None:
    assert Lot.from_raw_many({"totalItems": 0}) == []

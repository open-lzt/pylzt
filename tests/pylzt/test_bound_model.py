"""Bound models — `lot.refresh()` and aiogram-style client binding through `execute`."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from pylzt.client import Client
from pylzt.errors import ModelNotBound
from pylzt.lib.clock import FakeClock
from pylzt.models.lot import Lot, LotFilter
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.types import Category, Currency, ItemId, ItemOrigin, SellerId, TokenId


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


def _raw(item_id: int, *, price: int = 100) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "category": "steam",
        "price": price,
        "price_currency": "rub",
        "title": f"Lot {item_id}",
        "item_state": "active",
        "item_origin": "resale",
        "guarantee": "24h",
        "nsb": False,
        "published_date": 1_700_000_000,
        "seller": {"user_id": 42},
    }


class _MarketTransport(BaseTransport):
    """Serves /{id}, /batch and a one-page listing — enough to bind every read path."""

    def __init__(self) -> None:
        super().__init__(token_pool=_pool())
        self.price = 100

    async def _send_raw(self, req: Request) -> Response:
        if req.path == "/batch":
            assert isinstance(req.json_body, list)
            ids = [job["id"] for job in req.json_body]
            jobs = {i: {"_job_result": "ok", "item": _raw(int(i))} for i in ids}
            return Response(status=200, body={"jobs": jobs})
        if req.path in ("/", "/steam"):
            return Response(status=200, body={"items": [_raw(1), _raw(2)], "perPage": 50})
        item_id = int(req.path.strip("/"))
        return Response(status=200, body={"item": _raw(item_id, price=self.price)})


def _unbound_lot(item_id: int = 9) -> Lot:
    return Lot(
        item_id=ItemId(item_id),
        category=Category.STEAM,
        price=Decimal("1"),
        currency=Currency.RUB,
        title="x",
        seller_id=SellerId(1),
        published_at=datetime.fromtimestamp(0, UTC),
        item_state="active",
        item_origin=ItemOrigin.RESALE,
        guarantee="",
        nsb=True,
        content_hash="h",
        attributes={},
    )


async def test_get_lot_is_bound_and_refreshes() -> None:
    transport = _MarketTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        lot = await client.market.get_lot(ItemId(5))
        transport.price = 80  # market moved
        fresh = await lot.refresh()

    assert int(fresh.item_id) == 5
    assert fresh.price == Decimal("80")  # re-fetched through the bound client


async def test_lots_from_listing_are_bound() -> None:
    async with Client(tokens=["tok"], transport=_MarketTransport()) as client:
        lots = await client.market.list_lots(LotFilter(category=Category.STEAM)).collect()
        refreshed = await lots[0].refresh()

    assert int(refreshed.item_id) == 1  # a paginated lot carries the client too


async def test_lots_from_batch_are_bound() -> None:
    async with Client(tokens=["tok"], transport=_MarketTransport()) as client:
        lots = await client.market.get_lots_batch([ItemId(1), ItemId(2)])
        refreshed = await lots[1].refresh()

    assert int(refreshed.item_id) == 2


async def test_unbound_model_raises_model_not_bound() -> None:
    with pytest.raises(ModelNotBound):
        await _unbound_lot().refresh()


def test_binding_does_not_affect_value_semantics() -> None:
    lot = _unbound_lot(1)
    twin = copy.deepcopy(lot)
    lot.as_(object())  # type: ignore[arg-type]  # bind to a dummy stand-in

    assert lot == twin  # _client is excluded from equality
    assert hash(lot) == hash(twin)  # …and from hash

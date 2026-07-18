"""Declarative `BaseMethod` — auto-build routing, auto-parse, and the import-time guards."""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ValidationError

from pylzt.errors import MethodDeclarationError
from pylzt.methods.base import BaseMethod, passthrough
from pylzt.methods.catalog import GetLot, GetLotsBatch
from pylzt.methods.categories import CategoryGames, CategoryParams, ListCategories
from pylzt.transport.base import Response
from pylzt.types import Category, HttpMethod, ItemId, RateClass


def _resp(body: dict[str, object]) -> Response:
    return Response(status=200, body=body)


def test_get_method_routes_fields_to_query_and_fills_path() -> None:
    class Search(BaseMethod[dict[str, object]]):
        __http_method__ = HttpMethod.GET
        __url__ = "/{category}/lots"
        __returning__ = passthrough

        category: Category
        page: int

    req = Search(category=Category.STEAM, page=3).build_request()
    assert req.method == HttpMethod.GET
    assert req.path == "/steam/lots"
    assert req.query == {"page": 3}  # non-path field → query string (GET default)
    assert req.json_body is None


def test_post_method_routes_fields_to_body() -> None:
    class Publish(BaseMethod[dict[str, object]]):
        __http_method__ = HttpMethod.POST
        __url__ = "/publish"
        __rate_class__ = RateClass.GENERAL
        __returning__ = passthrough

        title: str
        price: int

    req = Publish(title="x", price=10).build_request()
    assert req.method == HttpMethod.POST
    assert req.json_body == {"title": "x", "price": 10}  # POST default → body
    assert req.query == {}


def test_none_fields_are_dropped_from_the_wire() -> None:
    class Opt(BaseMethod[dict[str, object]]):
        __http_method__ = HttpMethod.GET
        __url__ = "/x"
        __returning__ = passthrough

        a: int | None = None
        b: int | None = None

    assert Opt(a=1).build_request().query == {"a": 1}  # b=None omitted


def test_returning_auto_parses_without_a_parse_override() -> None:
    # CategoryParams declares `__returning__ = passthrough` and no parse_response.
    method = CategoryParams(category=Category.STEAM)
    assert method.build_request().path == "/steam/params"
    assert method.parse_response(_resp({"min_price": 1})) == {"min_price": 1}


def test_get_lot_unwraps_item_envelope() -> None:
    req = GetLot(item_id=ItemId(42)).build_request()
    assert req.path == "/42"
    assert req.rate_class == RateClass.GENERAL


def test_list_categories_drops_unknown_slugs() -> None:
    parsed = ListCategories().parse_response(_resp({"categories": ["steam", "not-a-category"]}))
    assert parsed == [Category.STEAM]


def test_category_games_reads_games_or_items() -> None:
    method = CategoryGames(category=Category.STEAM)
    assert method.parse_response(_resp({"games": [{"id": 1}]})) == [{"id": 1}]
    assert method.parse_response(_resp({"items": [{"id": 2}]})) == [{"id": 2}]
    assert method.parse_response(_resp({"games": "bad"})) == []


def test_batch_orders_results_and_skips_absent() -> None:
    ids = [ItemId(1), ItemId(2), ItemId(3)]
    body: dict[str, object] = {
        "jobs": {
            "1": {"_job_result": "ok", "item": _lot_body(1)},
            "3": {"_job_result": "ok", "item": _lot_body(3)},
        }
    }  # 2 absent
    parsed = GetLotsBatch(item_ids=ids).parse_response(_resp(body))
    assert [int(lot.item_id) for lot in parsed] == [1, 3]  # input order kept, 2 skipped


def test_methods_are_frozen_with_no_handwritten_init() -> None:
    method = GetLot(item_id=ItemId(7))
    with pytest.raises(ValidationError):  # frozen → immutable
        method.item_id = ItemId(8)  # type: ignore[misc]
    assert GetLot(item_id=ItemId(7)) == GetLot(item_id=ItemId(7))  # value equality for free


def test_missing_url_raises_at_class_creation() -> None:
    with pytest.raises(MethodDeclarationError):

        class NoUrl(BaseMethod[int]):
            __returning__: ClassVar = passthrough


def test_missing_returning_raises_at_class_creation() -> None:
    with pytest.raises(MethodDeclarationError):

        class NoReturn(BaseMethod[int]):
            __url__ = "/x"


def test_path_dunder_is_rejected() -> None:
    with pytest.raises(MethodDeclarationError):

        class UsesPath(BaseMethod[int]):
            __path__ = "/x"
            __returning__: ClassVar = passthrough


def _lot_body(item_id: int) -> dict[str, object]:
    return {
        "item_id": item_id,
        "category": "steam",
        "price": 100,
        "price_currency": "rub",
        "title": f"Lot {item_id}",
        "item_state": "active",
        "item_origin": "resale",
        "guarantee": "24h",
        "nsb": False,
        "published_date": 1_700_000_000,
        "seller": {"user_id": 42},
    }

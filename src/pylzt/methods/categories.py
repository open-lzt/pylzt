"""Category methods — active category list and per-category filter schema.

Declarative `BaseMethod[T]` dataclasses. `CategoryParams` needs no `parse_response` —
its `__returning__ = passthrough` returns the body dict as-is. The per-category-params TTL cache is
**not** here: it's a `BaseCache` injected into the client (read-through at the client
boundary), so these stay pure. UNVERIFIED: `/params` and `/games` response shapes.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from pylzt.methods.base import BaseMethod, passthrough
from pylzt.models.category import CategoryGame, FilterSchema
from pylzt.types import Category, HttpMethod

if TYPE_CHECKING:
    from pylzt.transport.base import Response


class ListCategories(BaseMethod[list[Category]]):
    """Fetch the current list of active market categories (unknown slugs are dropped)."""

    __http_method__ = HttpMethod.GET
    # Real path, verified live: /categoryList 404s (it doesn't exist upstream).
    # /category is what AS7's Market client actually calls (`market.categories.list()`).
    __url__ = "/category"

    def parse_response(self, response: Response) -> list[Category]:
        # Real /category shape, verified live: "categories" is a list of category
        # OBJECTS (category_id, category_name, ...), not bare slug strings — pull
        # category_name out of each before constructing the enum.
        raw: list[dict[str, object]] = response.body.get("categories", [])
        result: list[Category] = []
        for entry in raw:
            slug = entry.get("category_name") if isinstance(entry, dict) else entry
            if not isinstance(slug, str):
                continue
            with suppress(ValueError):
                result.append(Category(slug))
        return result


class CategoryParams(BaseMethod[FilterSchema]):
    """Per-category filter schema from GET /:category/params. Returns the raw body dict."""

    __http_method__ = HttpMethod.GET
    __url__ = "/{category}/params"
    __returning__ = passthrough

    category: Category


class CategoryGames(BaseMethod[list[CategoryGame]]):
    """Games list for a category from GET /:category/games — `games` or `items` key."""

    __http_method__ = HttpMethod.GET
    __url__ = "/{category}/games"

    category: Category

    def parse_response(self, response: Response) -> list[CategoryGame]:
        raw = response.body.get("games") or response.body.get("items") or []
        if not isinstance(raw, list):
            return []
        return [g for g in raw if isinstance(g, dict)]

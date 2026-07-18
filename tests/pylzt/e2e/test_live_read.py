"""Live read-only smoke suite against the real lzt.market / lolz.live API.

Opt-in only (excluded from the default run via the `e2e` marker; `pytest -m e2e` to
run it) and skipped entirely without `LZT_E2E_TOKEN` set — a real bearer token never
belongs in source or CI secrets by default. Every request here is `HttpMethod.GET`;
nothing in this module mutates account state.
"""

from __future__ import annotations

import inspect
import os
import pkgutil
from collections.abc import AsyncIterator
from importlib import import_module
from typing import Any

import pytest

import pylzt.methods as methods_pkg
from pylzt.client import Client
from pylzt.errors import BadRequest, Forbidden, NotFound
from pylzt.methods.base import BaseMethod
from pylzt.models.lot import LotFilter
from pylzt.types import Category, Currency, HttpMethod

pytestmark = pytest.mark.e2e

_TOKEN = os.environ.get("LZT_E2E_TOKEN", "").strip()
if not _TOKEN:
    pytest.skip("LZT_E2E_TOKEN not set — skipping live e2e read suite", allow_module_level=True)

# A permission/scope/lookup gap is an expected shape for an arbitrary token hitting an
# arbitrary endpoint (the JWT `scope` claim is a curated subset, and some endpoints need
# resource state this account doesn't have) — xfail, don't fail the whole discovery
# sweep over it. Anything else (5xx, rate limiting, a parse error) propagates for real.
_EXPECTED_GAPS = (Forbidden, NotFound, BadRequest)


def _discover_get_methods_with_args() -> list[tuple[type[BaseMethod[Any]], tuple[str, ...]]]:
    """Every declared GET `BaseMethod` subclass that has at least one required field —
    the complement of `_discover_get_methods`'s zero-arg set. Paired with its required
    field names so the test can resolve each one live instead of guessing a value."""
    seen: dict[str, tuple[type[BaseMethod[Any]], tuple[str, ...]]] = {}
    for modinfo in pkgutil.iter_modules(methods_pkg.__path__, methods_pkg.__name__ + "."):
        module = import_module(modinfo.name)
        for name, obj in vars(module).items():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseMethod)
                and obj is not BaseMethod
                and obj.__module__ == module.__name__
                and not obj.__abstract__
                and obj.__url__
                and obj.__http_method__ is HttpMethod.GET
            ):
                required = tuple(f for f, info in obj.model_fields.items() if info.is_required())
                if required:
                    seen[name] = (obj, required)
    return sorted(seen.values(), key=lambda pair: pair[0].__name__)


def _discover_get_methods() -> list[type[BaseMethod[Any]]]:
    """Every declared `BaseMethod` subclass (generated + hand-written) that is a GET
    with no required fields — callable with zero arguments, safe to fan out over
    generically instead of hand-listing every read endpoint.

    Pydantic injects the synthetic parametrized submodel it mints for every
    `class Foo(BaseMethod[Resp])` (named e.g. `BaseMethod[CategoryResponse[Item]]`)
    into the declaring module's globals, for forward-ref/pickle resolution — it shows
    up in `vars(module)` right next to real endpoint classes. `__url__` is empty on
    those (only a literal `class Foo(BaseMethod[Resp]): __url__ = "..."` sets it), so
    filtering on it excludes the noise without reaching into pydantic internals.
    """
    seen: dict[str, type[BaseMethod[Any]]] = {}
    for modinfo in pkgutil.iter_modules(methods_pkg.__path__, methods_pkg.__name__ + "."):
        module = import_module(modinfo.name)
        for name, obj in vars(module).items():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseMethod)
                and obj is not BaseMethod
                and obj.__module__ == module.__name__
                and not obj.__abstract__
                and obj.__url__
                and obj.__http_method__ is HttpMethod.GET
                and not any(f.is_required() for f in obj.model_fields.values())
            ):
                seen[name] = obj
    return sorted(seen.values(), key=lambda c: c.__name__)


GET_ZERO_ARG_METHODS = _discover_get_methods()
GET_METHODS_WITH_ARGS = _discover_get_methods_with_args()


def _first(response: Any, *list_attrs: str) -> Any | None:
    """Pull the first item out of a list response or the first populated list-valued
    attribute on a wrapper response — response shapes vary per endpoint, ids don't.

    `getattr(response, "items", None)` would silently return the builtin `dict.items`
    bound method on a plain-dict response instead of a field — guard with `isinstance`.
    """
    items = response if isinstance(response, list) else None
    if items is None:
        for attr in list_attrs:
            candidate = getattr(response, attr, None)
            if isinstance(candidate, list) and candidate:
                items = candidate
                break
    return items[0] if items else None


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    # Function-scoped: a module-scoped Client binds its httpx async resources to the
    # first test's event loop, then breaks ("Event loop is closed") once pytest-asyncio
    # hands the next test a fresh loop (the default per-test loop_scope). Client
    # construction is I/O-free, so per-test recreation costs nothing real.
    c = Client([_TOKEN])
    try:
        yield c
    finally:
        await c.aclose()


@pytest.mark.parametrize("method_cls", GET_ZERO_ARG_METHODS, ids=lambda c: c.__name__)
async def test_zero_arg_get_endpoint(client: Client, method_cls: type[BaseMethod[Any]]) -> None:
    """Every auto-discovered zero-argument GET endpoint parses without raising."""
    try:
        await client.execute(method_cls())
    except _EXPECTED_GAPS as exc:
        pytest.xfail(f"{method_cls.__name__}: {exc!r} (scope/permission/lookup gap for this token)")


# Resolvers for GET methods that DO have required fields — one real live value per field
# name, fetched from whichever endpoint actually carries that kind of id, not a guessed
# constant. A field with no resolver here means the test skips that method rather than
# invent a value that could either 404 misleadingly or (worse) silently hit the wrong
# resource. Every resolver's target endpoint/attribute is verified live before being
# trusted here (never guessed from memory — see codegen-runbook.md's own rule for this).
_ThreadForum = tuple[int, int]


async def _resolve_thread_and_forum(client: Client) -> _ThreadForum | None:
    """(thread_id, forum_id) from the first thread of the first visible forum — one
    shared live lookup so both fields don't each trigger their own forums_list/threads_list."""
    forums_resp = await client.forum.forums_list()
    forum = _first(forums_resp, "forums")
    if forum is None:
        return None
    threads_resp = await client.forum.threads_list(forum_id=forum.forum_id)
    thread = _first(threads_resp, "threads", "items")
    if thread is None:
        return None
    return thread.thread_id, forum.forum_id


async def _resolve_item_id(client: Client) -> int | None:
    lots = await client.market.list_lots(LotFilter(category=Category.STEAM)).collect(limit=1)
    return lots[0].item_id if lots else None


async def _resolve_link_id(client: Client) -> int | None:
    link = _first(await client.forum.links_list(), "link_forums")
    return link.link_id if link is not None else None


async def _resolve_page_id(client: Client) -> int | None:
    page = _first(await client.forum.pages_list(), "pages")
    return page.page_id if page is not None else None


async def _resolve_popular_tags(client: Client) -> dict[str, str] | None:
    # TagsPopular is `passthrough` (no response model) — the body is a bare
    # {"tags": {"<tag_id>": "<tag name>", ...}} dict, not an attribute-bearing model.
    body = await client.forum.tags_popular()
    tags = body.get("tags") if isinstance(body, dict) else None
    return tags or None


class _CachedResolvers:
    """Memoizes each multi-field live lookup for the lifetime of one test session's
    client — 20 methods needing `thread_id` shouldn't each re-fetch the thread list."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    async def get(self, client: Client, field: str) -> Any | None:
        if field in self._cache:
            return self._cache[field]
        value = await self._resolve(client, field)
        self._cache[field] = value
        return value

    async def _resolve(self, client: Client, field: str) -> Any | None:
        if field in ("thread_id", "forum_id"):
            pair = await _resolve_thread_and_forum(client)
            if pair is None:
                return None
            thread_id, forum_id = pair
            self._cache["thread_id"] = thread_id
            self._cache["forum_id"] = forum_id
            return self._cache[field]
        if field == "item_id":
            return await _resolve_item_id(client)
        if field == "link_id":
            return await _resolve_link_id(client)
        if field == "page_id":
            return await _resolve_page_id(client)
        if field in ("tag", "tag_id"):
            tags = await _resolve_popular_tags(client)
            if not tags:
                return None
            value = int(next(iter(tags))) if field == "tag_id" else next(iter(tags.values()))
            return value
        if field == "user_id":
            return "me"
        if field == "category":
            return Category.STEAM
        if field == "currency":
            return Currency.USD
        return None


@pytest.fixture(scope="module")
def resolvers() -> _CachedResolvers:
    # Module-scoped (not function-scoped like `client`): the whole point is sharing one
    # live lookup per field across every parametrized case in this module.
    return _CachedResolvers()


@pytest.mark.parametrize(
    "method_cls,required",
    GET_METHODS_WITH_ARGS,
    ids=lambda v: v.__name__ if isinstance(v, type) else None,
)
async def test_get_endpoint_with_resolved_args(
    client: Client,
    resolvers: _CachedResolvers,
    method_cls: type[BaseMethod[Any]],
    required: tuple[str, ...],
) -> None:
    """Every auto-discovered GET endpoint that has required fields, resolved with real
    live values instead of the zero-arg-only subset `test_zero_arg_get_endpoint` covers."""
    kwargs: dict[str, Any] = {}
    for field in required:
        value = await resolvers.get(client, field)
        if value is None:
            pytest.skip(
                f"{method_cls.__name__}: no live resolver/value for required field {field!r}"
            )
        kwargs[field] = value
    try:
        await client.execute(method_cls(**kwargs))
    except _EXPECTED_GAPS as exc:
        pytest.xfail(f"{method_cls.__name__}: {exc!r} (scope/permission/lookup gap for this token)")


async def test_market_category_lot_chain(client: Client) -> None:
    """`list_categories` -> `category_params` -> `list_lots` -> `get_lot`, exercising
    the hand-written Client read path end to end, not just declared-endpoint discovery."""
    categories = await client.market.list_categories()
    assert categories

    schema = await client.market.category_params(Category.STEAM)
    assert schema is not None

    lots = await client.market.list_lots(LotFilter(category=Category.STEAM)).collect(limit=3)
    if not lots:
        pytest.skip("no live Steam lots returned — nothing to chain get_lot against")

    lot = await client.market.get_lot(lots[0].item_id)
    assert lot.item_id == lots[0].item_id


async def test_forum_forum_thread_chain(client: Client) -> None:
    """`forums_list` -> `forums_get` -> `threads_list` -> `threads_get`, chaining real
    ids harvested from the live account instead of guessing fixed ones."""
    forums_resp = await client.forum.forums_list()
    forum = _first(forums_resp, "forums")
    if forum is None:
        pytest.skip("no forums visible to this token — nothing to chain forums_get against")

    assert await client.forum.forums_get(forum.forum_id) is not None

    threads_resp = await client.forum.threads_list(forum_id=forum.forum_id)
    thread = _first(threads_resp, "threads", "items")
    if thread is None:
        pytest.skip(f"forum {forum.forum_id} has no visible threads to chain threads_get against")

    thread_detail = await client.forum.threads_get(thread.thread_id)
    assert thread_detail.thread_id == thread.thread_id

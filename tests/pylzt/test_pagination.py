"""`Paginator` — async page-walking + the additive `on_page_start` checkpoint hook."""

from __future__ import annotations

import pytest

from pylzt.pagination import Page, Paginator


def _pages(*chunks: list[int]) -> list[Page[int]]:
    return [Page(items=chunk, has_more=(i < len(chunks) - 1)) for i, chunk in enumerate(chunks)]


async def test_paginator_walks_all_pages_without_hook() -> None:
    pages = _pages([1, 2], [3, 4], [5])

    async def fetch(page: int) -> Page[int]:
        return pages[page - 1]

    items = [item async for item in Paginator(fetch)]
    assert items == [1, 2, 3, 4, 5]


async def test_on_page_start_fires_before_each_fetch_in_order() -> None:
    pages = _pages([1], [2], [3])
    seen_before_fetch: list[int] = []

    async def fetch(page: int) -> Page[int]:
        # the hook must have already recorded this page before fetch runs
        assert seen_before_fetch[-1] == page
        return pages[page - 1]

    async def on_page_start(page: int) -> None:
        seen_before_fetch.append(page)

    items = [item async for item in Paginator(fetch, on_page_start=on_page_start)]
    assert items == [1, 2, 3]
    assert seen_before_fetch == [1, 2, 3]


async def test_on_page_start_omitted_leaves_behavior_unchanged() -> None:
    pages = _pages([1, 2])

    async def fetch(page: int) -> Page[int]:
        return pages[page - 1]

    items = [item async for item in Paginator(fetch)]
    assert items == [1, 2]


async def test_on_page_start_exception_propagates_not_swallowed() -> None:
    async def fetch(page: int) -> Page[int]:
        return Page(items=[page], has_more=False)

    async def on_page_start(page: int) -> None:
        raise RuntimeError("checkpoint failed")

    with pytest.raises(RuntimeError, match="checkpoint failed"):
        async for _ in Paginator(fetch, on_page_start=on_page_start):
            pass

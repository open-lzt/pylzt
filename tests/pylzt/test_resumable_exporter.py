"""`ResumableExporter` — crash-resume, natural-exhaustion clear, early-break persist."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pylzt.export.resumable_exporter import ResumableExporter
from pylzt.pagination import Page
from pylzt.storage import MemoryCursorStorage


def _fetcher(pages: dict[int, list[int]]) -> Callable[[int], Awaitable[Page[int]]]:
    async def fetch(page: int) -> Page[int]:
        items = pages.get(page, [])
        has_more = page < max(pages)
        return Page(items=items, has_more=has_more)

    return fetch


async def test_resumes_from_last_checkpoint_after_simulated_crash() -> None:
    storage = MemoryCursorStorage()
    pages = {1: [1, 2], 2: [3, 4], 3: [5, 6]}
    fetch = _fetcher(pages)

    seen: list[int] = []
    exporter = ResumableExporter("exp1", fetch, storage)
    async for item in exporter:
        seen.append(item)
        # crash right after the checkpoint for page 2 has been written (item 3
        # is page 2's first item) — page 1 is fully behind us
        if item == 3:
            break

    assert seen == [1, 2, 3]
    cursor = await storage.load_cursor("exp1")
    assert cursor is not None
    assert cursor.next_page == 2  # checkpoint written before page 2's fetch

    # "restart the process": new ResumableExporter instance, same export_id+storage
    resumed = ResumableExporter("exp1", fetch, storage)
    resumed_items = [item async for item in resumed]

    # skipped page 1 entirely; re-fetched page 2 in full (at-least-once — item 3
    # may repeat across the crash boundary, never silently dropped)
    assert resumed_items == [3, 4, 5, 6]


async def test_natural_exhaustion_clears_the_cursor() -> None:
    storage = MemoryCursorStorage()
    fetch = _fetcher({1: [1, 2], 2: [3]})

    items = [item async for item in ResumableExporter("exp1", fetch, storage)]

    assert items == [1, 2, 3]
    assert await storage.load_cursor("exp1") is None


async def test_early_break_leaves_cursor_saved() -> None:
    storage = MemoryCursorStorage()
    fetch = _fetcher({1: [1, 2], 2: [3, 4]})

    async for item in ResumableExporter("exp1", fetch, storage):
        if item == 1:
            break

    cursor = await storage.load_cursor("exp1")
    assert cursor is not None  # not cleared — the async-for never fully drained

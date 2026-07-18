"""A long-running export that survives a crash by checkpointing its
`Paginator` cursor to `BaseCursorStorage` before each page fetch."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from pylzt.pagination import Page, Paginator
from pylzt.storage import BaseCursorStorage, ExportCursor


class ResumableExporter[T]:
    """Wraps a `Paginator` with crash-safe cursor persistence, keyed by
    `export_id`. Resumes from the last checkpointed page if one exists;
    clears the cursor only when the export fully drains (an early `break`
    by the caller leaves the cursor in place for a future resume)."""

    def __init__(
        self,
        export_id: str,
        fetch: Callable[[int], Awaitable[Page[T]]],
        storage: BaseCursorStorage,
        *,
        max_pages: int | None = None,
    ) -> None:
        self._export_id = export_id
        self._fetch = fetch
        self._storage = storage
        self._max_pages = max_pages

    async def __aiter__(self) -> AsyncIterator[T]:
        saved = await self._storage.load_cursor(self._export_id)
        start_page = saved.next_page if saved is not None else 1
        walked = saved.walked if saved is not None else 0

        async def on_page_start(page: int) -> None:
            nonlocal walked
            await self._storage.save_cursor(
                ExportCursor(export_id=self._export_id, next_page=page, walked=walked)
            )
            walked += 1

        paginator = Paginator(
            self._fetch,
            start_page=start_page,
            max_pages=self._max_pages,
            on_page_start=on_page_start,
        )
        async for item in paginator:
            yield item
        await self._storage.clear_cursor(self._export_id)

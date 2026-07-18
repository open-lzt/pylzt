"""Generic async paginator (Law 22 — hide `page`/`has_more` behind `async for`).

The caller writes `async for lot in client.list_lots(filter)`; page fetching,
the has-more check, and empty-page termination live here once.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

from pydantic import BaseModel, ConfigDict


class Page[T](BaseModel):
    model_config = ConfigDict(frozen=True)

    items: Sequence[T]
    has_more: bool


class Paginator[T]:
    """Lazily walks pages via an injected `fetch(page) -> Page[T]`."""

    def __init__(
        self,
        fetch: Callable[[int], Awaitable[Page[T]]],
        *,
        start_page: int = 1,
        max_pages: int | None = None,
        on_page_start: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        self._fetch = fetch
        self._start = start_page
        self._max_pages = max_pages
        self._on_page_start = on_page_start

    async def __aiter__(self) -> AsyncIterator[T]:
        page = self._start
        walked = 0
        while True:
            if self._on_page_start is not None:
                await self._on_page_start(page)
            result = await self._fetch(page)
            for item in result.items:
                yield item
            walked += 1
            if not result.has_more or not result.items:
                return
            if self._max_pages is not None and walked >= self._max_pages:
                return
            page += 1

    async def first_page(self) -> Sequence[T]:
        """Convenience: fetch just the first page (demo / smoke use)."""
        return (await self._fetch(self._start)).items

    async def collect(self, *, limit: int | None = None) -> list[T]:
        """Drain into a list, optionally capped at `limit` items."""
        out: list[T] = []
        async for item in self:
            out.append(item)
            if limit is not None and len(out) >= limit:
                break
        return out

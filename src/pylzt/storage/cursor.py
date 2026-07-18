"""Persistence seam for a resumable exporter's pagination cursor.

Same shape as `lib/cache.py`'s `BaseCache` / `storage/batch.py`'s `BaseStorage`: an
ABC behind the consumer, an in-memory default (`MemoryCursorStorage`). Distinct
from `BaseStorage` (batch-job history) — a cursor is a different persisted
concept (one row per `export_id`, overwritten in place, never "committed").
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict


class ExportCursor(BaseModel):
    """Resume point for one long-running export. `next_page` is the page to
    fetch next, saved BEFORE that page is fetched — a crash mid-page
    re-fetches (and re-yields) that whole page on resume rather than
    silently skipping its items (at-least-once, not exactly-once)."""

    model_config = ConfigDict(frozen=True)

    export_id: str
    next_page: int
    walked: int = 0


class BaseCursorStorage(ABC):
    @abstractmethod
    async def save_cursor(self, cursor: ExportCursor) -> None:
        """Upsert — overwrites any existing cursor for `cursor.export_id`."""

    @abstractmethod
    async def load_cursor(self, export_id: str) -> ExportCursor | None:
        """The saved cursor for `export_id`, or `None` if never started / cleared."""

    @abstractmethod
    async def clear_cursor(self, export_id: str) -> None:
        """Delete the cursor. Call only on natural exhaustion (export complete)."""


class MemoryCursorStorage(BaseCursorStorage):
    def __init__(self) -> None:
        self._cursors: dict[str, ExportCursor] = {}

    async def save_cursor(self, cursor: ExportCursor) -> None:
        self._cursors[cursor.export_id] = cursor

    async def load_cursor(self, export_id: str) -> ExportCursor | None:
        return self._cursors.get(export_id)

    async def clear_cursor(self, export_id: str) -> None:
        self._cursors.pop(export_id, None)

"""`MemoryCursorStorage` — save/load/clear round-trip for exporter resume state."""

from __future__ import annotations

from pylzt.storage import ExportCursor, MemoryCursorStorage


async def test_round_trip_save_then_load() -> None:
    storage = MemoryCursorStorage()
    cursor = ExportCursor(export_id="exp1", next_page=3, walked=2)

    await storage.save_cursor(cursor)

    assert await storage.load_cursor("exp1") == cursor


async def test_load_unknown_export_id_returns_none() -> None:
    storage = MemoryCursorStorage()
    assert await storage.load_cursor("nope") is None


async def test_clear_then_load_returns_none() -> None:
    storage = MemoryCursorStorage()
    await storage.save_cursor(ExportCursor(export_id="exp1", next_page=1))

    await storage.clear_cursor("exp1")

    assert await storage.load_cursor("exp1") is None


async def test_save_is_an_upsert_not_a_duplicate() -> None:
    storage = MemoryCursorStorage()
    await storage.save_cursor(ExportCursor(export_id="exp1", next_page=1))
    await storage.save_cursor(ExportCursor(export_id="exp1", next_page=5, walked=4))

    cursor = await storage.load_cursor("exp1")
    assert cursor is not None
    assert cursor.next_page == 5
    assert cursor.walked == 4


async def test_clear_unknown_export_id_is_a_noop() -> None:
    storage = MemoryCursorStorage()
    await storage.clear_cursor("never-existed")  # must not raise

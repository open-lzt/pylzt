"""Sync-over-async: a real, separately-typed synchronous counterpart per async
method (codegen-generated), not a Pyrogram-style runtime monkey-patch that
erases static types. See `runner.py`/`client.py`."""

from __future__ import annotations

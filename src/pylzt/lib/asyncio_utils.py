"""Small asyncio helpers shared across `Client` and its namespaces (2+ call sites —
`client.py`'s `execute_batch` and `facades/_namespace.py`'s `MarketNamespace.get_lots_batch`
— extracted here rather than imported cross-module to avoid a `client.py` <-> `facades`
import cycle)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from typing import cast


async def gather_or_raise[R](aws: Iterable[Awaitable[R]]) -> list[R]:
    """`asyncio.gather` with `return_exceptions=True` so a failing awaitable never
    orphans its siblings mid-flight (bare `gather` propagates the first exception but
    leaves the rest running unawaited in the background) — then re-raises the first
    exception found, preserving plain `gather`'s "fail on first error" contract for
    the caller once every awaitable has actually finished."""
    results = await asyncio.gather(*aws, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return cast("list[R]", results)

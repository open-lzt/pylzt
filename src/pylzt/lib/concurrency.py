"""Resizable concurrency gate — the primitive an AIMD governor tunes live.

`asyncio.Semaphore` has no API to change its permit count after construction.
`AdaptiveGate` is structurally the same thing (a counter + a FIFO waiter
queue) except `resize()` is a plain synchronous method, safe to call from a
non-async callback (e.g. `BaseTransport.send`'s response handler). Growing
wakes queued waiters immediately; shrinking is lazy — an in-flight holder
over the new limit finishes naturally, never forcibly evicted/cancelled.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class AdaptiveGate:
    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        self._limit = limit
        self._in_flight = 0
        self._waiters: deque[asyncio.Future[None]] = deque()

    @property
    def limit(self) -> int:
        return self._limit

    def resize(self, new_limit: int) -> None:
        if new_limit < 1:
            raise ValueError(f"limit must be >= 1, got {new_limit}")
        self._limit = new_limit
        self._wake_waiters()

    def _wake_waiters(self) -> None:
        while self._waiters and self._in_flight < self._limit:
            fut = self._waiters.popleft()
            if not fut.done():
                self._in_flight += 1
                fut.set_result(None)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        if self._in_flight < self._limit:
            self._in_flight += 1
        else:
            fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            self._waiters.append(fut)
            try:
                await fut
            except asyncio.CancelledError:
                if fut.cancelled():
                    # Never granted a slot — drop the stale entry so _wake_waiters
                    # doesn't have to scan past it later.
                    with contextlib.suppress(ValueError):
                        self._waiters.remove(fut)
                else:
                    # _wake_waiters already resolved fut and counted it in _in_flight
                    # before this task's cancellation could be delivered — the slot
                    # was granted but never claimed, so give it back or it leaks
                    # forever (a permanently-lower effective limit).
                    self._in_flight -= 1
                    self._wake_waiters()
                raise
        try:
            yield
        finally:
            self._in_flight -= 1
            self._wake_waiters()

"""Background-thread event loop — the sync-over-async substrate.

`asyncio.run()` per call would raise `RuntimeError` if invoked from inside a
caller's own already-running event loop; a dedicated background thread with its
own loop sidesteps that entirely (the same approach other sync-over-async
wrapper libraries use), at the cost of one always-alive thread once started.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any


class SyncRunner:
    """Owns a background event-loop thread, started lazily on first `run()`.
    `run()` blocks the calling thread until the coroutine completes; safe to
    call from a plain sync script or from inside another running event loop."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        # Guards loop lifecycle (start/submit/stop) as one critical section — a `run()`
        # that reads `self._loop` and submits to it must not race a concurrent `close()`
        # that stops that same loop in between, or the submitted coroutine never runs
        # and `future.result()` hangs forever (the loop it was scheduled on already
        # stopped). `close()` only holds the lock while clearing the reference; the
        # actual stop+join happens outside it so it never blocks a `run()` that's
        # already past the lock and waiting on its own future.
        self._lock = threading.Lock()

    def _ensure_started_locked(self) -> asyncio.AbstractEventLoop:
        """Must be called while holding `self._lock`."""
        if self._loop is not None:
            return self._loop
        ready = threading.Event()
        loop_holder: list[asyncio.AbstractEventLoop] = []

        def _run_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop_holder.append(loop)
            ready.set()
            try:
                loop.run_forever()
            finally:
                loop.close()  # release the loop's own resources once stopped

        thread = threading.Thread(target=_run_loop, daemon=True, name="pylzt-sync-runner")
        thread.start()
        ready.wait()
        self._loop = loop_holder[0]
        self._thread = thread
        return self._loop

    def run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        with self._lock:
            loop = self._ensure_started_locked()
            future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def close(self) -> None:
        """Stop the loop and join the thread. Idempotent — a second call is a no-op."""
        with self._lock:
            if self._loop is None or self._thread is None:
                return
            loop, thread = self._loop, self._thread
            self._loop = None
            self._thread = None
        loop.call_soon_threadsafe(loop.stop)
        thread.join()

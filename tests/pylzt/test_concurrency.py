"""`AdaptiveGate` — resizable concurrency gate (grow wakes waiters, shrink is lazy)."""

from __future__ import annotations

import asyncio

import pytest

from pylzt.lib.concurrency import AdaptiveGate


def test_rejects_nonpositive_initial_limit() -> None:
    with pytest.raises(ValueError, match="limit must be >= 1"):
        AdaptiveGate(0)


def test_rejects_nonpositive_resize() -> None:
    gate = AdaptiveGate(4)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        gate.resize(0)


async def test_acquire_under_limit_does_not_block() -> None:
    gate = AdaptiveGate(2)
    async with gate.acquire():
        pass  # released cleanly, no hang


async def test_grow_wakes_a_queued_waiter_immediately() -> None:
    gate = AdaptiveGate(1)
    entered_second = asyncio.Event()

    async def holder() -> None:
        async with gate.acquire():
            await asyncio.sleep(10)  # would hang the test if not cancelled

    async def waiter() -> None:
        async with gate.acquire():
            entered_second.set()

    holder_task = asyncio.create_task(holder())
    await asyncio.sleep(0.01)  # let holder acquire first
    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0.01)  # waiter is now queued, gate at limit=1

    gate.resize(2)  # grow — should wake the queued waiter without releasing holder
    await asyncio.wait_for(entered_second.wait(), timeout=1.0)

    holder_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder_task
    await waiter_task


async def test_shrink_does_not_evict_in_flight_holder() -> None:
    gate = AdaptiveGate(2)
    async with gate.acquire():
        gate.resize(1)  # shrink below current in-flight count
        # still inside the context — must not raise or forcibly exit
    # after release, a single new acquire must respect the new (lower) limit
    async with gate.acquire():
        pass


async def test_cancellation_while_waiting_does_not_corrupt_in_flight_count() -> None:
    gate = AdaptiveGate(1)

    async def holder() -> None:
        async with gate.acquire():
            await asyncio.sleep(10)

    holder_task = asyncio.create_task(holder())
    await asyncio.sleep(0.01)

    waiter_task = asyncio.create_task(gate.acquire().__aenter__())
    await asyncio.sleep(0.01)  # waiter queued, blocked
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    holder_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder_task

    # gate must still work correctly for a fresh caller afterward
    async with gate.acquire():
        pass


async def test_cancellation_after_grant_returns_the_reservation() -> None:
    """A waiter can be woken (fut resolved, _in_flight incremented) and then
    cancelled before it resumes into the `try:` body — the granted slot must
    not leak, or the gate permanently loses one unit of capacity per race."""
    gate = AdaptiveGate(1)

    holder_cm = gate.acquire()
    await holder_cm.__aenter__()  # in_flight = 1, gate full

    waiter_task = asyncio.create_task(gate.acquire().__aenter__())
    await asyncio.sleep(0)  # let the waiter queue up and block on `await fut`

    # Release the only slot — _wake_waiters() resolves the waiter's future
    # synchronously (no `await` in between), but the waiter task hasn't been
    # resumed by the loop yet.
    await holder_cm.__aexit__(None, None, None)

    # Cancel the waiter in this same window: its future is already done, so
    # Future.cancel() can't cancel it — CPython instead throws CancelledError
    # into the task at its next resumption.
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    assert gate._in_flight == 0  # reservation given back, not leaked

    # A fresh caller must be able to acquire immediately — no lost capacity.
    async with asyncio.timeout(1.0), gate.acquire():
        pass

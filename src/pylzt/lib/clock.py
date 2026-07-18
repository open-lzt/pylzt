"""Injectable monotonic + wall clock so time-based logic is deterministic in tests.

Rate buckets and proxy cooldowns need an elapsed-seconds source; `occurred_at`
needs UTC wall time. Both go through `Clock` so a `FakeClock` makes the math
reproducible (the token-bucket refill is load-bearing — a bug means bans).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime


class Clock(ABC):
    @abstractmethod
    def monotonic(self) -> float:
        """Seconds from an arbitrary fixed point; only deltas are meaningful."""

    @abstractmethod
    def now(self) -> datetime:
        """Current wall time, always timezone-aware UTC."""


class RealClock(Clock):
    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock(Clock):
    """Manually advanced clock for deterministic tests."""

    def __init__(self, *, start_monotonic: float = 0.0, start: datetime | None = None) -> None:
        self._mono = start_monotonic
        self._wall = start or datetime(2026, 1, 1, tzinfo=UTC)

    def monotonic(self) -> float:
        return self._mono

    def now(self) -> datetime:
        return self._wall

    def advance(self, seconds: float) -> None:
        self._mono += seconds
        self._wall = self._wall.fromtimestamp(self._wall.timestamp() + seconds, tz=UTC)

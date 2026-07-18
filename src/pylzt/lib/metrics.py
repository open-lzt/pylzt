"""Metrics seam (Law 27) — libs emit through this, never `import prometheus`.

The daemon binds a real Prometheus adapter; tests and the library default use the
no-op `NullMetrics`, so `import pylzt` pulls in no metrics backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping


class BaseMetrics(ABC):
    @abstractmethod
    def incr(self, name: str, value: int = 1, **labels: str) -> None: ...

    @abstractmethod
    def gauge(self, name: str, value: float, **labels: str) -> None: ...

    @abstractmethod
    def observe(self, name: str, value: float, **labels: str) -> None: ...


class NullMetrics(BaseMetrics):
    def incr(self, name: str, value: int = 1, **labels: str) -> None:
        return None

    def gauge(self, name: str, value: float, **labels: str) -> None:
        return None

    def observe(self, name: str, value: float, **labels: str) -> None:
        return None


def merge_labels(base: Mapping[str, str], extra: Mapping[str, str]) -> dict[str, str]:
    return {**base, **extra}

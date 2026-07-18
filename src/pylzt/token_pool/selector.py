"""Token selection strategy — which token the pool tries first (open-closed seam).

`RoundRobinTokenPool` delegates the *order* it tries tokens to a `BaseTokenSelector`;
the pool still enforces each token's per-class rate budget (`try_consume`), so a
selector only reprioritises, it can never bypass the limiter. Ship fair round-robin as
the default; a consumer injects a weighted / least-recently-used / health-aware
strategy by passing `selector=` — no edit to the pool.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from pylzt.token_pool.base import Token


class BaseTokenSelector(ABC):
    @abstractmethod
    def candidates(self, tokens: Sequence[Token]) -> Sequence[Token]:
        """Live tokens in the order to try for budget (first = most preferred)."""

    def on_leased(self, token: Token, tokens: Sequence[Token]) -> None:
        """Advance internal state after `token` was successfully leased. Default no-op."""


class RoundRobinSelector(BaseTokenSelector):
    """Fair rotation across the live fleet — the default, so no token starves."""

    def __init__(self) -> None:
        self._cursor = 0

    def candidates(self, tokens: Sequence[Token]) -> Sequence[Token]:
        n = len(tokens)
        if n == 0:
            return ()
        start = self._cursor % n
        return [tokens[(start + i) % n] for i in range(n)]

    def on_leased(self, token: Token, tokens: Sequence[Token]) -> None:
        if token in tokens:
            self._cursor = tokens.index(token) + 1

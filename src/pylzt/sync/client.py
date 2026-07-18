"""Synchronous facade over `Client` — same constructor args, blocking methods,
every return type matching its async counterpart's unwrapped type (mypy --strict
clean, unlike a Pyrogram-style runtime monkey-patch, which loses this).
"""

from __future__ import annotations

from typing import Any

from pylzt.client import Client
from pylzt.facades._sync_namespace import (
    SyncAntipublicNamespace,
    SyncForumNamespace,
    SyncMarketNamespace,
)
from pylzt.sync.runner import SyncRunner


class SyncClient:
    """Not a `Client` subclass — wraps one internally, same composition pattern
    as the async namespaces. `close()`/context-manager usage stops both the
    wrapped `Client`'s transports and the background `SyncRunner` thread."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._async_client = Client(*args, **kwargs)
        self._runner = SyncRunner()
        self._closed = False
        self.market = SyncMarketNamespace(self._async_client.market, self._runner)
        self.forum = SyncForumNamespace(self._async_client.forum, self._runner)
        self.antipublic = SyncAntipublicNamespace(self._async_client.antipublic, self._runner)

    def close(self) -> None:
        """Idempotent — safe to call twice, and safe to skip if used only as a
        context manager. A second call is a no-op rather than re-spinning the
        runner's background thread just to close an already-closed client."""
        if self._closed:
            return
        self._closed = True
        self._runner.run(self._async_client.aclose())
        self._runner.close()

    def __enter__(self) -> SyncClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

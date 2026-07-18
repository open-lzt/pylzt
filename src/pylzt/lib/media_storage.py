"""Optional byte-cache for uploaded media, keyed by content hash.

Not an upload-dedup mechanism — a consumer looks up/audits previously uploaded bytes,
it does not skip the HTTP call for a hash it's seen before (the API's idempotency
contract for repeated uploads is unverified).
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from pathlib import Path

from pylzt.media import Media


class BaseMediaStorage(ABC):
    """A consumer implements a local file store, S3/remote-hosting store, etc."""

    @abstractmethod
    async def get(self, key: str) -> Media | None:
        """Return the cached Media for `key` (its sha256), or None if absent."""

    @abstractmethod
    async def save(self, key: str, media: Media) -> None:
        """Persist `media` under `key` (its sha256). Best-effort — a raised exception
        here must never fail the upload itself (see client.py wiring)."""


class NullMediaStorage(BaseMediaStorage):
    """Default: no-op, mirrors NullMetrics/NullProxyPool (off unless a consumer opts in)."""

    async def get(self, key: str) -> Media | None:
        return None

    async def save(self, key: str, media: Media) -> None:
        return None


class FileMediaStorage(BaseMediaStorage):
    """Local-disk `BaseMediaStorage` — one raw-bytes file per key plus a `.json`
    sidecar carrying `filename`/`content_type` (bytes alone can't round-trip those).

    Blocking file I/O runs via `asyncio.to_thread` so a save/get never stalls the
    event loop's other in-flight requests. A raised `OSError` (permission denied,
    disk full, ...) propagates from `save()`/`get()` as-is — `Client._save_media`
    already wraps every `media_storage.save()` call in `contextlib.suppress`, so
    this class itself has no reason to also swallow errors (fail loud once, at
    the one boundary that's supposed to absorb it, not silently everywhere else).
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _paths(self, key: str) -> tuple[Path, Path]:
        return self._root / key, self._root / f"{key}.json"

    async def get(self, key: str) -> Media | None:
        return await asyncio.to_thread(self._get_sync, key)

    def _get_sync(self, key: str) -> Media | None:
        data_path, meta_path = self._paths(key)
        if not data_path.is_file() or not meta_path.is_file():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return Media(
            data=data_path.read_bytes(),
            filename=meta["filename"],
            content_type=meta["content_type"],
        )

    async def save(self, key: str, media: Media) -> None:
        await asyncio.to_thread(self._save_sync, key, media)

    def _save_sync(self, key: str, media: Media) -> None:
        data_path, meta_path = self._paths(key)
        data_path.write_bytes(media.data)
        meta_path.write_text(
            json.dumps({"filename": media.filename, "content_type": media.content_type}),
            encoding="utf-8",
        )

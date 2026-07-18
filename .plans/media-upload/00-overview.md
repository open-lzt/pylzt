# Media upload — overview

**Tier:** module-lite (`--fast`) · **Mode:** layered · solo, one pass.
**Slug:** `media-upload` · root: `.plans/media-upload/`

## Goal

Give the 4 existing file-upload endpoints (`UsersAvatarUpload`, `UsersAvatarCrop`,
`UsersBackgroundUpload`, `UsersBackgroundCrop` — `methods/forum_users.py`) a real typed
file field instead of silently dropping the payload (today they only declare `user_id`,
no file field at all — uploads are currently impossible through this SDK). Add multipart
support end-to-end: a `Media` type → `Request.files` → `HttpxSession` → automatic routing
in `BaseMethod.build_request` → optional byte-cache via `BaseMediaStorage` on `Client`.
Codegen auto-detects `format: binary` spec fields so future upload endpoints get this for
free on the next `dev.codegen build`.

## Scope

1. `src/pylzt/media.py` (new) — `Media` frozen dataclass + `sha256` property.
2. `transport/base.py` — add `Request.files` field.
3. `transport/session.py` — `HttpxSession._raw_send` passes `files=`/`data=` when present.
4. `methods/base.py` — `BaseMethod.build_request` detects `Media`-typed fields, routes
   them to `files`, routes the rest to multipart `data` (not `json_body`) when any exist.
5. `lib/media_storage.py` (new) — `BaseMediaStorage` ABC + `NullMediaStorage` default.
6. `client.py` — `Client.__init__` gains `media_storage: BaseMediaStorage | None = None`;
   `execute()` saves successfully-uploaded `Media` into it (fire-and-forget, best-effort).
7. `dev/codegen/generator.py` — map OpenAPI `format: "binary"` request fields to `Media`
   instead of `str`; regenerate `forum_users.py`'s 4 upload methods to pick it up.

## Non-goals

- **No automatic upload dedup/skip.** `BaseMediaStorage` caches bytes that were already
  uploaded (for a caller to look up / audit / avoid re-reading a file from disk) — it does
  **not** skip the HTTP call for a hash it's seen before. The API's own idempotency
  contract for repeated uploads is unknown and out of scope; skipping the call on a cache
  hit would be an unverified assumption about server behavior. Revisit if a live check
  confirms the API treats identical uploads as safe no-ops.
- No streaming upload (large-file chunked transfer) — `Media.data: bytes` only, in line
  with avatar/background-sized payloads (small images), not general file transfer.
- No change to non-upload methods' request building (json_body path is untouched).

## Key types (frozen contract)

```python
# src/pylzt/media.py
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class Media:
    """A file to upload. `content_type` defaults to octet-stream when unset."""
    data: bytes
    filename: str
    content_type: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @classmethod
    def from_path(cls, path: str | Path, *, content_type: str | None = None) -> Media:
        p = Path(path)
        return cls(data=p.read_bytes(), filename=p.name, content_type=content_type)
```

```python
# transport/base.py — Request gains one field (frozen dataclass, slots=True unchanged)
files: Mapping[str, Media] | None = None
```

```python
# lib/media_storage.py
from abc import ABC, abstractmethod
from pylzt.media import Media

class BaseMediaStorage(ABC):
    """Optional byte-cache for uploaded media, keyed by content hash. Not an upload-dedup
    mechanism — see Non-goals. A consumer implements a local file store, S3/remote-hosting
    store, etc. by subclassing."""

    @abstractmethod
    async def get(self, key: str) -> Media | None:
        """Return the cached Media for `key` (its sha256), or None if absent."""

    @abstractmethod
    async def save(self, key: str, media: Media) -> None:
        """Persist `media` under `key` (its sha256). Best-effort — a raised exception
        here must never fail the upload itself (see client.py wiring, T6)."""

class NullMediaStorage(BaseMediaStorage):
    """Default: no-op, mirrors NullMetrics/NullProxyPool (off unless a consumer opts in)."""

    async def get(self, key: str) -> Media | None:
        return None

    async def save(self, key: str, media: Media) -> None:
        return None
```

## Decisions (autonomous, tagged)

- **`Media` lives at `src/pylzt/media.py` (top-level), not `models/`** — it's a transport
  concern (request body shape), not a wire-response DTO; `models/` is exclusively for
  `LolzObject`/`BoundModel` response parsing. `unverified` (naming call, no prior art in
  repo to confirm against — reasonable given `models/_MODULE.md`'s stated scope).
- **`BaseMediaStorage` default = `NullMediaStorage`, not `MemoryStorage`-style in-process
  dict** — caching arbitrary uploaded bytes in memory by default risks unbounded growth
  for a library whose `Client` may run long-lived. `verified-by-code:src/pylzt/lib/metrics.py:24`
  and `src/pylzt/proxy_pool/sticky.py:101` (`NullMetrics`/`NullProxyPool` are the
  established opt-in-only-by-default convention for anything that holds unbounded state).
- **`Client.execute`'s `media_storage.save()` call is wrapped, never lets a storage bug
  fail a real upload** — `save()` runs after the transport already returned 2xx; a broken
  custom storage impl must not turn a successful upload into a client-visible error.
  `unverified` (no live API check; this is a defensive-programming default per the
  project's own "fail loud except at a fire-and-forget boundary" convention).
- **`BaseMethod.build_request` routes ALL non-Media fields to multipart `data=` (not
  `json_body`) the moment any Media field is present** — httpx doesn't support `json=`
  together with `files=` (content-type conflict). `verified-by-code:src/pylzt/transport/session.py:90-104`
  (current `_raw_send` always sends `json=req.json_body`; can't coexist with `files=`).

## Worktree

`../pylzt-media-upload` on branch `feat/media-upload`, based on `main`.

## Risks (see also inline per-task acceptance)

- httpx multipart + query params together: `client.request(method, path, params=..., files=..., data=...)` — need a quick sandbox check that httpx accepts `data=` (dict) alongside `files=` for the non-file fields (it does per httpx docs: `data=` is form-encoded, `files=` is multipart, both together produce one multipart body). Task T3 acceptance covers this.
- Existing 4 upload methods currently have **no file field at all** (`user_id` only per
  the explore-agent read) — regenerating them via codegen is required for this feature to
  do anything observable; T7 must actually touch `forum_users.py`, not just the generator.
- `Media.from_path` reads the whole file into memory (`bytes`) — acceptable given the
  small-image-upload use case (see Non-goals); would need revisiting for large files.

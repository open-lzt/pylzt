"""A file to upload — the request-body counterpart of a wire-response DTO.

Lives at top level, not `models/`, because it's a transport concern (request shape),
not a response parsed via `LolzObject`/`BoundModel`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Media(BaseModel):
    """A file to upload. `content_type` defaults to octet-stream when unset."""

    model_config = ConfigDict(frozen=True)

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

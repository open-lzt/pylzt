"""Forum notification — the immutable domain view of a `/notifications` entry.

`content_type` shapes the payload differently per notification kind (a new-message
notification carries different keys than a rating one); modeling every variant as its
own dataclass would mean tracking the upstream's full, undocumented content-type
vocabulary. `extra` is the deliberate catch-all for whatever `content_type` doesn't
promote to a named field — the parser still narrows the three fields every notification
is known to carry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from collections.abc import Mapping

_KNOWN_KEYS = ("notification_id", "content_type", "create_date")


class Notification(BaseModel):
    model_config = ConfigDict(frozen=True)

    notification_id: int = 0
    content_type: str = ""
    created_at: int = 0
    extra: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> Notification:
        """`created_at` renames the wire's `create_date`; `extra` collects every key
        outside `_KNOWN_KEYS` — both need building before validation, everything else
        maps 1:1 onto its wire key."""
        payload = {
            "notification_id": raw.get("notification_id"),
            "content_type": raw.get("content_type"),
            "created_at": raw.get("create_date"),
            "extra": {k: v for k, v in raw.items() if k not in _KNOWN_KEYS},
        }
        return cls.model_validate({k: v for k, v in payload.items() if v is not None})

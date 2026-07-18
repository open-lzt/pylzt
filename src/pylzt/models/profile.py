"""Forum self-profile — the parsed view of `GET /users/me` (rating counters).

`Profile` is the typed shape `RatingPoller` diffs `user_like_count`/`user_dislike_count`
against on each cadence tick; the raw wire dict never escapes `Profile.from_raw`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Mapping


class Profile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    user_id: int = 0
    username: str = ""
    user_like_count: int = 0
    user_dislike_count: int = 0

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> Profile:
        return cls.model_validate({k: v for k, v in raw.items() if v is not None})

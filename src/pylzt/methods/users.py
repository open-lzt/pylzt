"""Forum user-profile read methods — declarative `BaseMethod[T]` operations.

`GetSelfProfile` fetches the authenticated account's own Forum profile, used by
`RatingPoller` to source `user_like_count`/`user_dislike_count` for diffing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylzt.methods.base import BaseMethod
from pylzt.models.profile import Profile
from pylzt.types import ApiTarget, HttpMethod, RateClass

if TYPE_CHECKING:
    from pylzt.transport.base import Response


class GetSelfProfile(BaseMethod[Profile]):
    """Fetch the authenticated account's own Forum profile."""

    __http_method__ = HttpMethod.GET
    __url__ = "/users/me"
    __api__ = ApiTarget.FORUM
    __rate_class__ = RateClass.FORUM

    def parse_response(self, response: Response) -> Profile:
        return Profile.from_raw(response.body.get("user", response.body))

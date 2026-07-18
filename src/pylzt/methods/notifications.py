"""Forum notification feed — `GET /notifications`, the Forum-host analog of `catalog.py`.

Backs `NotificationsPoller`'s cheap-check (`notifications_total`) + page fetch for both
the `market` and `nomarket` kinds; see `research/api-events-sources.md` rows 10/11/28/30/31.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from pylzt.methods.base import BaseMethod
from pylzt.models.notification import Notification
from pylzt.pagination import Page
from pylzt.types import ApiTarget, HttpMethod, RateClass

if TYPE_CHECKING:
    from typing import Any

    from pylzt.transport.base import Response


class ListNotifications(BaseMethod[Page[Notification]]):
    """One page of the Forum notification feed, scoped by `type`."""

    __http_method__ = HttpMethod.GET
    __url__ = "/notifications"
    __api__ = ApiTarget.FORUM
    __rate_class__ = RateClass.FORUM
    __query_fields__ = frozenset({"type", "limit"})

    type: str
    limit: int

    def parse_response(self, response: Response) -> Page[Notification]:
        notifications = _parse_notifications(response.body)
        total = int(response.body.get("notifications_total", len(notifications)) or 0)
        has_more = len(notifications) >= self.limit and total > len(notifications)
        return Page(items=notifications, has_more=has_more)


def _parse_notifications(envelope: Mapping[str, Any]) -> list[Notification]:
    raw = envelope.get("notifications", [])
    if isinstance(raw, Mapping):
        items: list[Any] = list(raw.values())
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    return [Notification.from_raw(item) for item in items if isinstance(item, Mapping)]

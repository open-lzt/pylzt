"""Hand-patched — a live `/list/states` capture (2026-07-05) shows `stickyLimit` absent
(the response instead carries `stickySlotsLimit`/`usedStickySlots`/`remainingStickySlots`/
`isStickyLimitVisible`, none of which the OpenAPI spec declares and `extra="ignore"`
already drops harmlessly). Loosened the spec's own field to nullable rather than guess at
a rename — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class UserItemStatesStickied(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/liststates"""

    item_state: str
    item_count: int
    title: str
    stickyLimit: int | None = None

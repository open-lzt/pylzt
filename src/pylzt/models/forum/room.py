"""Hand-patched — codegen declared `deal_id: str` (required) from the OpenAPI spec, but
a live `/chatbox` response (2026-07-05) returns `null` for every non-deal chat room.
Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api forum` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class Room(LolzObject):
    """Docs: https://lolzteam.readme.io/reference/chatboxindex"""

    can_report: bool
    deal_id: str | None = None
    eng: bool
    market: bool
    room_id: int
    title: str

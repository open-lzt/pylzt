"""Hand-patched — codegen declared `ban: str` (required) from the OpenAPI spec, but a
live `/chatbox` response (2026-07-05) returns `null` for an account with no active ban.
Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api forum` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject
from pylzt.models.forum.ignore import Ignore
from pylzt.models.forum.permissions import Permissions
from pylzt.models.forum.room import Room
from pylzt.models.forum.rooms_online import RoomsOnline


class ChatboxIndexResponse(LolzObject):
    """Docs: https://lolzteam.readme.io/reference/chatboxindex"""

    rooms: list[Room]
    ban: str | None = None
    ignore: list[Ignore]
    permissions: Permissions
    commands: list[str]
    roomsOnline: RoomsOnline

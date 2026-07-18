"""Hand-patched — codegen declared `list` as a required `dict[str, CategorySteamList]`,
but a live category search (2026-07-05) shows the API returns `[]` (an empty list, not
an empty dict) when the account owns no full games — loosened to accept both shapes.
Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pylzt.models.base import LolzObject
from pylzt.models.market.category_steam_list import CategorySteamList


class ItemSteamFullGames(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/categorysteam"""

    list: dict[str, CategorySteamList] | list[Any]
    total: int

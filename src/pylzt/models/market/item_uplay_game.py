"""Hand-patched — a live `uplay_games` capture (2026-07-05) shows `pvpTimePlayed`/
`pveTimePlayed` absent on a meaningful fraction of per-game entries (games with no
played-time telemetry omit both), while the OpenAPI spec declares them required. Loosened
to nullable — see docs/codegen-runbook.md.

Promoting this out of codegen intentionally clashes with the next `dev.codegen build --api
market` (`_guard_no_clobber`).
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class ItemUplayGame(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/categoryuplay"""

    title: str
    img: str
    pvpTimePlayed: int | None = None
    pveTimePlayed: int | None = None
    abbr: str
    gameId: str

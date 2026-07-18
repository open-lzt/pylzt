"""Hand-patched — a live `eg_games` capture (2026-07-05) shows `category_id`, `ru`, and
`hits_count` absent on a meaningful fraction of the per-game entries (each game legitimately
omits stats it doesn't track), while the OpenAPI spec declares all three required. Loosened
to nullable — see docs/codegen-runbook.md.

Promoting this out of codegen intentionally clashes with the next `dev.codegen build --api
market` (`_guard_no_clobber`).
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class ItemEgGame(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/categoryepicgames"""

    internal_game_id: int
    app_id: str
    title: str
    abbr: str
    category_id: int | None = None
    img: str
    url: str
    ru: str | None = None
    hits_count: int | None = None
    link: str

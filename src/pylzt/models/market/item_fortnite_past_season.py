"""Hand-patched — a live `fortnitePastSeasons` capture (2026-07-05) shows every field here
except `seasonLevel`/`bookLevel`/`seasonNumber` legitimately absent on a meaningful fraction
of per-season entries (older/lighter seasons don't carry the full stat set), while the
OpenAPI spec declares them all required. Loosened to nullable — see docs/codegen-runbook.md.

Promoting this out of codegen intentionally clashes with the next `dev.codegen build --api
market` (`_guard_no_clobber`).
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class ItemFortnitePastSeason(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/categoryfortnite"""

    numWins: int | None = None
    seasonXp: int | None = None
    purchasedVIP: bool | None = None
    survivorPrestige: int | None = None
    seasonLevel: int
    numLowBracket: int | None = None
    bookLevel: int
    numRoyalRoyales: int | None = None
    seasonNumber: int
    survivorTier: int | None = None
    numHighBracket: int | None = None

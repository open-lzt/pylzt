"""Hand-patched — a live category search (2026-07-05, riot_item.py fifth pass) showed
`WeaponSkins` as a slot-index -> skin-id map (`dict[str, str]`) on an account with
partial valorant data, not the spec-declared list — widened to accept both shapes.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class ItemValorantInventory(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/categoryriot"""

    WeaponSkins: dict[str, str] | list[str]
    Agent: list[str]
    Buddy: list[str]

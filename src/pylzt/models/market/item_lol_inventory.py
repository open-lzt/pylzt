"""Hand-patched — codegen declared `Skin` as `list[int]`, but a live category search
(2026-07-05) shows it's a champion-slot -> skin-id map (`{"0": 43008, "2": 427011, ...}`)
on some listings. `Champion` is left as `list[int]`: no live listing failed on it, so
the plain-list shape is confirmed for that field specifically.

Second pass (same date, after re-running the e2e suite against the first-pass fix):
`Skin` also comes back as a plain `list[int]` (same shape as `Champion`) on other
listings, not just the keyed map — widened to `dict[str, int] | list[int]` to accept
both observed shapes rather than picking one.

Promoting this out of codegen intentionally clashes with the next
`dev.codegen build --api market` (`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class ItemLolInventory(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/categoryriot"""

    Champion: list[int]
    Skin: dict[str, int] | list[int]

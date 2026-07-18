"""Hand-patched — a live `/balance/payout/services` capture (2026-07-05) shows two spec
mismatches. `p2p` is absent for every system on this account (no p2p payout configured).
`providers` is not the fixed `{BEP20, TRC20, ERC20, ...}` object the spec declares — real
keys are provider-pair codes (`SOL_USDC`, `BSC_BNB`, `TRON_USDT`, ...), a dynamic map like
`eg_games`/`uplay_games` (see `epic_games_item.py`/`uplay_item.py`), or `[]` when the
system has no configured providers. Retyped to the dynamic-map shape, `ProvidersBEP20`
kept as the per-provider value model since its `title`/`isUnavailable` fields still match
— see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from pylzt.models.base import LolzObject
from pylzt.models.market.providers_bep20 import ProvidersBEP20


class System(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/paymentspayoutservices"""

    system: str
    commission: str
    min: int
    max: int
    instant_payout: bool
    problematic_payout: bool
    is_unavailable: bool
    p2p: bool | None = None
    has_wallet: bool
    providers: dict[str, ProvidersBEP20] | list[Any] = Field(default_factory=list)

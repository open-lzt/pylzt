"""Hand-patched — codegen declared `noMarket` (camelCase) from the OpenAPI spec, but a
live `/profile/claims` capture (2026-07-05) returns the sibling key lowercase (`nomarket`),
so it never matched and always validated as missing. Aliased to the real wire key instead
of just loosening to nullable — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pydantic import Field

from pylzt.models.base import LolzObject
from pylzt.models.market.stats_market import StatsMarket


class Stats(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/profileclaims"""

    market: StatsMarket
    no_market: StatsMarket = Field(alias="nomarket")

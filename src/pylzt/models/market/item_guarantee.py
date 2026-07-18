"""Hand-patched — `endDate`/`active`/`cancelled`/`remainingTime` were declared required
`str`, but a live check (2026-07-05, CategoryBattleNet + CategorySteam, 40 items each)
shows every listing's `guarantee` sub-object carries `None` for all four — no listing
across either category had an active guarantee, so nullability is the only fact a live
capture can confirm here; the base type is kept `str` pending a sample with an actual
active guarantee to confirm its real shape. See docs/codegen-runbook.md.
"""

from __future__ import annotations

from pydantic import Field

from pylzt.models.base import LolzObject


class ItemGuarantee(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/categorybattlenet"""

    duration: int
    class_: str = Field(alias="class")
    durationPhrase: str
    endDate: str | None = None
    active: str | None = None
    cancelled: str | None = None
    remainingTime: str | None = None

"""Account balance — one currency's available + held funds on lzt.market.

Money is `Decimal`, never `float` (per code-quality rule); the wire sends amounts
as strings/numbers that parse losslessly through `str(...)` before `Decimal(...)`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Mapping


class Balance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    currency: str = ""
    balance: Decimal = Decimal(0)
    hold: Decimal = Decimal(0)

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> Balance:
        return cls.model_validate({k: v for k, v in raw.items() if v is not None})

"""Payment operation — the parsed, typed shape of a single `/user/payments` entry.

Assumption (unverified — no live capture of this endpoint's response shape yet, per
`research/api-events-sources.md`): the API returns a numeric `amount`/`sum` field, not
the display string seen in the research notes (e.g. `"+900.00 ₽"`). `_parse_amount`
below tolerates both — it strips any non-numeric characters (sign, currency symbol,
whitespace) before building the `Decimal`, so a live response in either shape parses
without a second code path. Flag this for confirmation once a real token is exercised.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Mapping


def _parse_amount(raw: Any) -> Decimal:
    if isinstance(raw, int | float):
        return Decimal(str(raw))
    cleaned = "".join(ch for ch in str(raw).strip() if ch.isdigit() or ch in "+-.")
    if not cleaned:
        return Decimal(0)
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal(0)


class PaymentOperation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    operation_id: int = 0
    operation_type: str = ""
    amount: Decimal = Decimal(0)
    currency: str = ""
    counterparty_id: int | None = None
    counterparty_username: str = ""
    fee: int = 0
    is_hold: bool = False
    hold_end_date: int | None = None
    item_id: int = 0
    comment: str = ""

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> PaymentOperation:
        """Wire→DTO parser for one `/user/payments` operation. No I/O, `extra="ignore"`.

        Counterparty/fee/comment are read from a nested `data` object when present
        (per research notes), falling back to the top level otherwise. `counterparty_id`/
        `hold_end_date` treat an empty string as absent (`None`), not `0` — everything
        else maps 1:1 onto its wire key, missing/`None` falls back to the field default.
        """
        data = raw.get("data")
        fields = data if isinstance(data, dict) else raw

        counterparty_id_raw = fields.get("user_id")
        counterparty_id = (
            int(counterparty_id_raw)
            if isinstance(counterparty_id_raw, int | str) and counterparty_id_raw != ""
            else None
        )

        hold_end_raw = raw.get("hold_end_date")
        hold_end_date = (
            int(hold_end_raw)
            if isinstance(hold_end_raw, int | str) and hold_end_raw != ""
            else None
        )

        payload = {
            "operation_id": raw.get("operation_id"),
            "operation_type": raw.get("operation_type"),
            "amount": _parse_amount(raw.get("amount", raw.get("sum", 0))),
            "currency": raw.get("currency"),
            "counterparty_id": counterparty_id,
            "counterparty_username": fields.get("username"),
            "fee": fields.get("fee"),
            "is_hold": raw.get("is_hold"),
            "hold_end_date": hold_end_date,
            "item_id": raw.get("item_id"),
            "comment": fields.get("comment"),
        }
        return cls.model_validate({k: v for k, v in payload.items() if v is not None})

    @classmethod
    def from_raw_many(cls, envelope: Mapping[str, Any]) -> list[PaymentOperation]:
        """Fan `from_raw` out over the `/user/payments` envelope's `operations`."""
        items = envelope.get("operations", [])
        if isinstance(items, dict):
            raws: list[Any] = list(items.values())
        elif isinstance(items, list):
            raws = items
        else:
            raws = []
        return [cls.from_raw(raw) for raw in raws if isinstance(raw, dict)]

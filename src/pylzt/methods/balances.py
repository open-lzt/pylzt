"""Account balances — one row per currency (RUB, USDT, etc.) on lzt.market.

Verified live 2026-07-03 against a real token: the real endpoint is `/balance/exchange`
(not `/user/balances` — that 404s; confirmed against AS7's own Market.md docs and a
live call). With no `from`/`to` params it returns the SAME primary balance twice,
nested under `from.balance` / `to.balance` (each `{balance_id, balance, ...}`, no
top-level `balances`/`items` list). Dedup by `balance_id`. Older envelope-key/mapping
fallbacks kept for forward-compat but UNVERIFIED against a live multi-currency
account — revisit if a real account ever returns more than one balance type here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pylzt.methods.base import BaseMethod
from pylzt.models.balance import Balance
from pylzt.types import HttpMethod, RateClass

if TYPE_CHECKING:
    from pylzt.transport.base import Response

_ENVELOPE_KEYS = ("balances", "items")


class GetBalances(BaseMethod[list[Balance]]):
    """Fetch every currency balance (available + hold) for the authenticated account."""

    __http_method__ = HttpMethod.GET
    __url__ = "/balance/exchange"
    __rate_class__ = RateClass.GENERAL

    def parse_response(self, response: Response) -> list[Balance]:
        return _parse_balances(response.body)


def _parse_balances(body: Mapping[str, Any]) -> list[Balance]:
    for key in _ENVELOPE_KEYS:
        raw = body.get(key)
        if isinstance(raw, list):
            return [Balance.from_raw(item) for item in raw if isinstance(item, Mapping)]

    # Real /balance/exchange shape: {"from": {"balance": {balance_id, balance, ...}},
    # "to": {"balance": {...}}} — dedup by balance_id (from/to are the same balance
    # when called with no explicit params).
    by_id: dict[str, Balance] = {}
    for side in ("from", "to"):
        wrapper = body.get(side)
        entry = wrapper.get("balance") if isinstance(wrapper, Mapping) else None
        if not isinstance(entry, Mapping):
            continue
        balance_id = str(entry.get("balance_id", side))
        by_id.setdefault(
            balance_id,
            Balance.from_raw({"currency": balance_id, "balance": entry.get("balance", 0)}),
        )
    if by_id:
        return list(by_id.values())

    # Fallback: currency-keyed mapping, e.g. {"RUB": {"balance": ..., "hold": ...}}.
    return [
        Balance.from_raw({"currency": currency, **fields})
        for currency, fields in body.items()
        if isinstance(fields, Mapping)
    ]

"""Payment operation types — the constant set the SDK was missing.

`PaymentOperation.operation_type` stays a plain `str` on purpose: the upstream set is open and
the API adds members without warning, so validating against this enum would turn a new operation
type into a parse failure. What the enum gives is a **source of truth to check against** — until
it existed, every consumer hardcoded its own string literals, and the downstream `lzt-eventus`
dispatch table got 9 of its 12 wrong: `cost` was written `expense`, `claim_hold` as
`hold_claimed`, `balance_exchange` as `exchange`, and `auto_payment` did not exist at all.
Each wrong value was a plausible paraphrase of a real one, which is exactly the failure a
constant prevents and a bare `str` cannot.

Members marked FILTERABLE are the documented `type` query values of `GET /user/payments`
(https://lzt-market.readme.io/reference/paymentshistory). `INCOME` and `COST` appear as
operation types in the wild and in AS7RIDENIED/LOLZTEAM's own constant table but are not in the
documented filter enum — they are response-only values.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["FILTERABLE_OPERATION_TYPES", "PaymentOperationType"]


class PaymentOperationType(StrEnum):
    # Response-only: observed as operation types, absent from the documented filter enum.
    INCOME = "income"
    COST = "cost"

    # Documented filter values.
    PAID_ITEM = "paid_item"
    SOLD_ITEM = "sold_item"
    WITHDRAWAL_BALANCE = "withdrawal_balance"
    REFILLED_BALANCE = "refilled_balance"
    INTERNAL_PURCHASE = "internal_purchase"
    MONEY_TRANSFER = "money_transfer"
    RECEIVING_MONEY = "receiving_money"
    CLAIM_HOLD = "claim_hold"
    INSURANCE_DEPOSIT = "insurance_deposit"
    PAID_MAIL = "paid_mail"
    CONTEST = "contest"
    INVOICE = "invoice"
    BALANCE_EXCHANGE = "balance_exchange"


#: The subset accepted by the `type` query parameter, in the order the docs list it.
FILTERABLE_OPERATION_TYPES: frozenset[PaymentOperationType] = frozenset(
    {
        PaymentOperationType.PAID_ITEM,
        PaymentOperationType.SOLD_ITEM,
        PaymentOperationType.WITHDRAWAL_BALANCE,
        PaymentOperationType.REFILLED_BALANCE,
        PaymentOperationType.INTERNAL_PURCHASE,
        PaymentOperationType.MONEY_TRANSFER,
        PaymentOperationType.RECEIVING_MONEY,
        PaymentOperationType.CLAIM_HOLD,
        PaymentOperationType.INSURANCE_DEPOSIT,
        PaymentOperationType.PAID_MAIL,
        PaymentOperationType.CONTEST,
        PaymentOperationType.INVOICE,
        PaymentOperationType.BALANCE_EXCHANGE,
    }
)

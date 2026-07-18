"""Payments read method — declarative `BaseMethod[T]` cursor page over `/user/payments`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylzt.methods.base import BaseMethod
from pylzt.models.payment import PaymentOperation
from pylzt.pagination import Page
from pylzt.types import HttpMethod, RateClass

if TYPE_CHECKING:
    from pylzt.transport.base import Response


class ListPayments(BaseMethod[Page[PaymentOperation]]):
    """Cursor page of `/user/payments`; `operation_id_lt` fetches operations older than it."""

    __http_method__ = HttpMethod.GET
    __url__ = "/user/payments"
    __query_fields__ = frozenset({"operation_id_lt", "type"})
    __rate_class__ = RateClass.GENERAL

    operation_id_lt: int | None = None
    type: str | None = None

    def parse_response(self, response: Response) -> Page[PaymentOperation]:
        operations = PaymentOperation.from_raw_many(response.body)
        return Page(items=operations, has_more=len(operations) > 0)

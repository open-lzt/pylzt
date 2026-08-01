"""Response envelopes for the three hand-written feed endpoints.

`/user/payments`, `/notifications` and `/conversations` are absent from the scraped spec that
`dev/codegen` builds from, so their methods were written by hand — and, unlike every generated
method, they carried no `__returning__` at all. They parse fine (each defines its own
`parse_response`), but a method with no declared response model is invisible to anything that
works off the model rather than off a live call: `lzt-testnet` synthesises its fake responses
from `__returning__`, so these four endpoints answered with an empty body and every consumer
downstream of them went untested.

These envelopes exist to declare that shape. The wire keys mirror what each method's own
`parse_response`/`from_raw_many` already reads, so declaring them changes no parsing behaviour —
`__returning__` only feeds the DEFAULT `parse_response`, which these methods override.
"""

from __future__ import annotations

from pydantic import Field

from pylzt.models.base import LolzObject
from pylzt.models.conversation import Conversation, Message
from pylzt.models.notification import Notification
from pylzt.models.payment import PaymentOperation

__all__ = [
    "ConversationMessagesListResponse",
    "ConversationsListResponse",
    "NotificationsListResponse",
    "PaymentsListResponse",
]


class PaymentsListResponse(LolzObject):
    """`GET /user/payments` — the documented envelope.

    The key is `payments`, per the endpoint's own OpenAPI block
    (https://lzt-market.readme.io/reference/paymentshistory). Operations arrive as an object
    keyed by operation id or as a plain array; `PaymentOperation.from_raw_many` accepts both,
    so the declared type is the array.
    """

    payments: list[PaymentOperation] = Field(default_factory=list)
    #: The API states pagination explicitly instead of leaving the caller to infer it from a
    #: page's length.
    has_next_page: bool = Field(default=False, alias="hasNextPage")
    last_operation_id: int | None = Field(default=None, alias="lastOperationId")


class NotificationsListResponse(LolzObject):
    """`GET /notifications` — the feed plus the total the cheap-check compares against."""

    notifications: list[Notification] = Field(default_factory=list)
    notifications_total: int = 0


class ConversationsListResponse(LolzObject):
    """`GET /conversations` — one page of the selected folder."""

    conversations: list[Conversation] = Field(default_factory=list)


class ConversationMessagesListResponse(LolzObject):
    """`GET /conversations/messages` — one page of a single conversation's messages."""

    messages: list[Message] = Field(default_factory=list)

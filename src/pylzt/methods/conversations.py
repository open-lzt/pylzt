"""Forum conversations read methods — declarative `BaseMethod[T]` ops against the Forum API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylzt.methods.base import BaseMethod
from pylzt.models.conversation import Conversation, Message
from pylzt.pagination import Page
from pylzt.types import ApiTarget, HttpMethod, RateClass

if TYPE_CHECKING:
    from pylzt.transport.base import Response


class ListConversations(BaseMethod[Page[Conversation]]):
    """Page of `/conversations`; `folder` selects the inbox view (e.g. `"unread"`/`"market"`)."""

    __http_method__ = HttpMethod.GET
    __url__ = "/conversations"
    __query_fields__ = frozenset({"folder"})
    __api__ = ApiTarget.FORUM
    __rate_class__ = RateClass.FORUM

    folder: str | None = None

    def parse_response(self, response: Response) -> Page[Conversation]:
        conversations = Conversation.from_raw_many(response.body)
        return Page(items=conversations, has_more=len(conversations) > 0)


class ListConversationMessages(BaseMethod[Page[Message]]):
    """Page of `/conversations/messages` for one conversation (`conversation_id` is a
    query param on the real API, not a path segment — verified against AS7's Forum
    client, `forum.conversations.messages.list()`)."""

    __http_method__ = HttpMethod.GET
    __url__ = "/conversations/messages"
    __query_fields__ = frozenset({"conversation_id"})
    __api__ = ApiTarget.FORUM
    __rate_class__ = RateClass.FORUM

    conversation_id: int

    def parse_response(self, response: Response) -> Page[Message]:
        messages = Message.from_raw_many(response.body)
        return Page(items=messages, has_more=len(messages) > 0)

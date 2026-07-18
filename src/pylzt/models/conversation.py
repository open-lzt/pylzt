"""Forum conversations — parsed, typed shapes of `/conversations` and its messages sub-resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Mapping


class Conversation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    conversation_id: int = 0
    conversation_title: str = ""
    creator_user_id: int = 0
    creator_username: str = ""
    conversation_update_date: int = 0
    is_unread: bool = False
    folder: str = ""

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> Conversation:
        """Wire→DTO parser for one `/conversations` entry. `creator_user_id`/
        `creator_username` come from a nested `creator_user` object when present,
        falling back to the flat wire keys otherwise — every other field maps
        1:1 onto its wire key, missing/`None` values fall back to the field default."""
        payload = dict(raw)
        creator = raw.get("creator_user")
        if isinstance(creator, dict):
            payload["creator_user_id"] = creator.get("user_id")
            payload["creator_username"] = creator.get("username")
        return cls.model_validate({k: v for k, v in payload.items() if v is not None})

    @classmethod
    def from_raw_many(cls, envelope: Mapping[str, Any]) -> list[Conversation]:
        """Fan `from_raw` out over the `/conversations` envelope's `conversations`."""
        items = envelope.get("conversations", [])
        if isinstance(items, dict):
            raws: list[Any] = list(items.values())
        elif isinstance(items, list):
            raws = items
        else:
            raws = []
        return [cls.from_raw(raw) for raw in raws if isinstance(raw, dict)]


class Message(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    message_id: int = 0
    conversation_id: int = 0
    creator_user_id: int = 0
    message_body_plain_text: str = ""
    message_create_date: int = 0
    message_is_system: bool = False

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> Message:
        """Wire→DTO parser for one `/conversations/{id}/messages` entry. `creator_user_id`
        comes from a nested `creator_user` object when present, falling back to the flat
        `message_creator_user_id` wire key otherwise — every other field maps 1:1 onto its
        wire key, missing/`None` values fall back to the field default."""
        payload = dict(raw)
        creator = raw.get("creator_user")
        payload["creator_user_id"] = (
            creator.get("user_id")
            if isinstance(creator, dict)
            else raw.get("message_creator_user_id")
        )
        return cls.model_validate({k: v for k, v in payload.items() if v is not None})

    @classmethod
    def from_raw_many(cls, envelope: Mapping[str, Any]) -> list[Message]:
        """Fan `from_raw` out over the `/conversations/{id}/messages` envelope's `messages`."""
        items = envelope.get("messages", [])
        if isinstance(items, dict):
            raws: list[Any] = list(items.values())
        elif isinstance(items, list):
            raws = items
        else:
            raws = []
        return [cls.from_raw(raw) for raw in raws if isinstance(raw, dict)]

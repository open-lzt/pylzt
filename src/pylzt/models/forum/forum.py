"""Hand-patched — codegen declared `forum_rules_thread_id: int` (required) and
`forum_moderators: list[str]` from the OpenAPI spec, but a live `/forums/feed-options` /
`/forums` response (2026-07-05) returns `null` for a forum with no dedicated rules thread,
and full moderator user objects (not usernames) for `forum_moderators`. Promoting this out
of codegen intentionally clashes with the next `dev.codegen build --api forum`
(`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pylzt.models.base import LolzObject
from pylzt.models.forum.forum_forum_prefixe import ForumForumPrefixe
from pylzt.models.forum.forum_links import ForumLinks
from pylzt.models.forum.forum_permissions import ForumPermissions


class Forum(LolzObject):
    """Docs: https://lolzteam.readme.io/reference/forumsgetfeedoptions"""

    forum_id: int
    forum_title: str
    forum_description: str
    forum_thread_count: int
    forum_post_count: int
    parent_node_id: int
    node_type_id: str
    icon_content: str
    active_icon_content: str
    forum_rules_thread_id: int | None = None
    isLike2Node: bool
    forum_prefixes: list[ForumForumPrefixe]
    thread_default_prefix_id: int
    thread_prefix_is_required: bool
    links: ForumLinks
    permissions: ForumPermissions
    forum_is_followed: bool
    forum_moderators: list[dict[str, Any]]

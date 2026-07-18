"""Hand-patched — NOT auto-generated. A live `/forums/feed-options` capture (2026-07-05,
353 forum entries) shows a consistently *lighter* per-forum shape than `/forums`
(`ForumsList`) returns: every entry carries exactly these 14 keys, none more. Reusing the
`Forum` model (shared with `ForumsList`, which legitimately needs `forum_thread_count`/
`forum_post_count`/`forum_prefixes`/`thread_default_prefix_id`/`thread_prefix_is_required`)
produced 1765 validation errors — those five fields are never present here, and this
endpoint adds one `Forum` doesn't have (`has_children`). A dedicated model for the
lighter shape is the correct fix, not loosening the shared `Forum` (that would make
`ForumsList`'s real required fields silently optional too) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pylzt.models.base import LolzObject
from pylzt.models.forum.forum_links import ForumLinks
from pylzt.models.forum.forum_permissions import ForumPermissions


class ForumFeedOption(LolzObject):
    """Docs: https://lolzteam.readme.io/reference/forumsgetfeedoptions"""

    forum_id: int
    forum_title: str
    forum_description: str
    parent_node_id: int
    node_type_id: str
    icon_content: str
    active_icon_content: str
    forum_rules_thread_id: int | None = None
    has_children: bool
    isLike2Node: bool
    links: ForumLinks
    permissions: ForumPermissions
    forum_is_followed: bool
    forum_moderators: list[dict[str, Any]]

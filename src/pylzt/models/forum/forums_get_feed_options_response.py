"""Hand-patched — `forums` reuses the shared `Forum` model in the OpenAPI spec, but a
live capture (2026-07-05) proved this endpoint returns a lighter per-forum shape; retyped
to the dedicated `ForumFeedOption` model — see `forum_feed_option.py` and
docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject
from pylzt.models.forum.forum_feed_option import ForumFeedOption


class ForumsGetFeedOptionsResponse(LolzObject):
    """Docs: https://lolzteam.readme.io/reference/forumsgetfeedoptions"""

    forums: list[ForumFeedOption]
    excluded_forums_ids: list[int]
    default_excluded_forums_ids: list[int]
    keywords: str

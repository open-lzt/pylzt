"""Hand-patched — a live `/chatbox/messages/leaderboard` capture (2026-07-05) shows
`avatar_date`, `background_date`, `custom_title`, `display_style_group_id`, `uniq_banner`,
`uniq_username_css`, and `short_link` absent/null on a meaningful fraction of entries
(accounts with no avatar/background/custom-title/uniq-banner/profile-short-link set omit
the corresponding field entirely), while the OpenAPI spec declares all seven required.
Loosened to nullable — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject
from pylzt.models.forum.leaderboard_rendered import LeaderboardRendered
from pylzt.models.forum.leaderboard_uniq_banner import LeaderboardUniqBanner


class Leaderboard(LolzObject):
    """Docs: https://lolzteam.readme.io/reference/chatboxgetleaderboard"""

    count: int
    user_id: int
    avatar_date: int | None = None
    background_date: int | None = None
    contest_count: int
    custom_title: str | None = None
    display_banner_id: int
    display_icon_group_id: int
    display_style_group_id: int | None = None
    is_banned: bool
    last_activity: int
    like2_count: int
    like_count: int
    message_count: int
    register_date: int
    rendered: LeaderboardRendered
    short_link: str | None = None
    trophy_points: int
    uniq_banner: LeaderboardUniqBanner | None = None
    uniq_username_css: str | None = None
    username: str

"""Hand-patched — `restore_percents` was declared a required `int`, but a live check
(2026-07-05, across most `ItemSeller`-backed categories) shows it absent whenever the
seller hasn't triggered a restore-percentage calculation — loosened to nullable. See
docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class ItemSeller(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/categorybattlenet"""

    user_id: int
    sold_items_count: int
    active_items_count: int
    restore_data: str
    username: str
    avatar_date: int
    is_banned: int
    display_style_group_id: int
    restore_percents: int | None = None

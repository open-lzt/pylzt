"""Hand-patched — `restore_percents` was declared `str`, a plain copy-paste bug: the
sibling `ItemSeller` model declares the identical field as `int`, and a live check
(2026-07-05, `int_type` validation errors expecting int) confirms `int` is correct.
Also nullable — same live check shows it absent for sellers with no restore-percentage
calculation yet, matching `ItemSeller`. See docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class CategoryDiscordItemSeller(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/categorydiscord"""

    user_id: int
    sold_items_count: int
    active_items_count: int
    restore_data: str
    username: str
    avatar_date: int
    is_banned: int
    display_style_group_id: int
    restore_percents: int | None = None

"""Hand-patched — a live `/forums/grouped` capture (2026-07-05) shows only `link_title`
and `isDefault` present on every tab (7/7); `title`/`isHidden`/`tabLink`/`isDynamicTitle`
are present on some tabs but not others, and `node_ids`/`isExtendedTab`/`prefixes`/
`prefixes_not`/`order`/`direction`/`period`/`state`/`q` (the search-tab filter fields) are
absent on every tab in this capture — a plain link-tab carries none of them. Loosened all
but the two always-present fields to nullable — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class Tab(LolzObject):
    """Docs: https://lolzteam.readme.io/reference/forumsgrouped"""

    link_title: str
    isDefault: bool
    title: str | None = None
    isHidden: bool | None = None
    tabLink: str | None = None
    isDynamicTitle: bool | None = None
    node_ids: str | None = None
    isExtendedTab: bool | None = None
    prefixes: list[str] | None = None
    prefixes_not: list[str] | None = None
    order: str | None = None
    direction: str | None = None
    period: str | None = None
    state: str | None = None
    q: str | None = None

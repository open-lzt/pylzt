"""Hand-patched — codegen declared `title`/`isHidden` (required) from the OpenAPI spec,
but a live `/forums` response (2026-07-05) omits either field on several tabs. Promoting
this out of codegen intentionally clashes with the next `dev.codegen build --api forum`
(`_guard_no_clobber`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pylzt.models.base import LolzObject


class ForumsListTab(LolzObject):
    """Docs: https://lolzteam.readme.io/reference/forumslist"""

    link_title: str
    isDefault: bool
    title: str | None = None
    isHidden: bool | None = None

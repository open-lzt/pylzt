"""Hand-patched — a live `/profile/get` capture (2026-07-05) shows `backgrounds` as `[]`
(no custom background set) instead of the spec's modeled object — widened to accept both
shapes — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pylzt.models.base import LolzObject
from pylzt.models.market.rendered_avatars import RenderedAvatars
from pylzt.models.market.rendered_backgrounds import RenderedBackgrounds


class UserRendered(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/profileget"""

    username: str
    avatars: RenderedAvatars
    backgrounds: RenderedBackgrounds | list[Any] | None = None
    link: str

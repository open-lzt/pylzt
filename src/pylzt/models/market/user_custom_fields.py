"""Hand-patched — a live `/profile/get` capture (2026-07-05) shows most of these LZT
custom-profile fields absent (each is only set once the account owner has configured it;
this account had only `_4`/`ban_reason`/`discord`/`github`/`jabber`/`lztUnbanAmount`/
`steam`/`telegram`/`vk`), while the OpenAPI spec declares all of them required. Loosened
every field but `_4` (present in the capture) to nullable — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from pydantic import Field

from pylzt.models.base import LolzObject


class UserCustomFields(LolzObject):
    """Docs: https://lzt-market.readme.io/reference/profileget"""

    field_4: str = Field(alias="_4")
    allowSelfUnban: list[str] | None = None
    ban_reason: str | None = None
    discord: str | None = None
    github: str | None = None
    jabber: str | None = None
    lztAwardUserTrophy: str | None = None
    lztLikesIncreasing: str | None = None
    lztLikesZeroing: str | None = None
    lztSympathyIncreasing: str | None = None
    lztSympathyZeroing: str | None = None
    lztUnbanAmount: str | None = None
    maecenasValue: str | None = None
    scamURL: str | None = None
    steam: str | None = None
    telegram: str | None = None
    vk: str | None = None
    favoritePorn: str | None = None
    favoriteVape: str | None = None
    favoriteAnime: str | None = None
    matrix: str | None = None

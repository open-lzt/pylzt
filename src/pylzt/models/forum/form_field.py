"""Hand-patched — a live `/forms/list` capture (2026-07-05) shows `fieldChoices` is not
the fixed `{buy, sell}` shape the OpenAPI spec declares (no field in the live account's
forms actually has `buy`/`sell` keys): it's a dynamic label map (e.g. `{"market": "Маркет",
"ru_1": ..., "sbp": ...}`) for fields with choices, or `[]` for fields with none. Retyped
to the dynamic-map shape (same pattern as `eg_games`/`uplay_games` in
`epic_games_item.py`/`uplay_item.py`) — see docs/codegen-runbook.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from pylzt.models.base import LolzObject


class FormField(LolzObject):
    """Docs: https://lolzteam.readme.io/reference/formslist"""

    field_id: int
    title: str
    fieldChoices: dict[str, str] | list[Any] = Field(default_factory=list)
    required: int
    max_length: int
    default_value: str

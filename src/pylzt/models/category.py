"""Category-endpoint boundary types.

The `/:category/params` filter schema and `/:category/games` entries are upstream JSON
whose exact field set is **UNVERIFIED** (no HAR capture yet — never invent a third-party
schema from memory). They are named here so the public return types are greppable,
documented boundary types instead of a bare `dict`. When a HAR capture confirms the
fields, promote each alias to a `TypedDict` / frozen DTO in one edit — call sites already
name the type, so nothing else changes.
"""

from __future__ import annotations

from collections.abc import Mapping

# One category's filter schema from GET /:category/params (UNVERIFIED shape).
FilterSchema = Mapping[str, object]

# One game entry from GET /:category/games (UNVERIFIED shape).
CategoryGame = Mapping[str, object]

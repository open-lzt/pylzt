"""Spec-drift detection: diff a freshly-scraped OpenAPI fragment against the
committed baseline in `dev/generated/openapi/lzt_*.json`.

Scope is deliberately narrow — path presence, per-schema required-field set,
and per-field resolved type (reused from `generator._schema_type`, not
re-derived). No description/example/summary diffing; that's not a shape
change and would make this noisy enough to ignore.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .generator import _schema_type
from .pipeline import SPEC_DIR, CodegenError
from .scraper import scrape_site


class FieldShapeChangeKind(StrEnum):
    ENDPOINT_ADDED = "endpoint_added"
    ENDPOINT_REMOVED = "endpoint_removed"
    SCHEMA_ADDED = "schema_added"
    SCHEMA_REMOVED = "schema_removed"
    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    FIELD_TYPE_CHANGED = "field_type_changed"
    REQUIRED_CHANGED = "required_changed"


@dataclass(frozen=True, slots=True)
class SpecDrift:
    kind: FieldShapeChangeKind
    path: str
    detail: str = ""


class SpecDiffError(CodegenError):
    """A spec-diff run couldn't complete (missing baseline, scrape failure)."""


def diff_specs(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[SpecDrift]:
    drift: list[SpecDrift] = []
    drift.extend(_diff_paths(baseline, candidate))
    drift.extend(_diff_schemas(baseline, candidate))
    return drift


def _diff_paths(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[SpecDrift]:
    base_paths = set(baseline.get("paths", {}))
    cand_paths = set(candidate.get("paths", {}))
    drift = [
        SpecDrift(FieldShapeChangeKind.ENDPOINT_REMOVED, f"paths.{p}")
        for p in sorted(base_paths - cand_paths)
    ]
    drift += [
        SpecDrift(FieldShapeChangeKind.ENDPOINT_ADDED, f"paths.{p}")
        for p in sorted(cand_paths - base_paths)
    ]
    return drift


def _diff_schemas(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[SpecDrift]:
    base_schemas: dict[str, Any] = baseline.get("components", {}).get("schemas", {})
    cand_schemas: dict[str, Any] = candidate.get("components", {}).get("schemas", {})
    drift: list[SpecDrift] = []

    for name in sorted(set(base_schemas) - set(cand_schemas)):
        drift.append(SpecDrift(FieldShapeChangeKind.SCHEMA_REMOVED, f"components.schemas.{name}"))
    for name in sorted(set(cand_schemas) - set(base_schemas)):
        drift.append(SpecDrift(FieldShapeChangeKind.SCHEMA_ADDED, f"components.schemas.{name}"))

    for name in sorted(set(base_schemas) & set(cand_schemas)):
        drift.extend(
            _diff_one_schema(baseline, base_schemas[name], candidate, cand_schemas[name], name)
        )
    return drift


def _diff_one_schema(
    baseline: dict[str, Any],
    base_schema: dict[str, Any],
    candidate: dict[str, Any],
    cand_schema: dict[str, Any],
    schema_name: str,
) -> list[SpecDrift]:
    drift: list[SpecDrift] = []
    base_required = set(base_schema.get("required", []))
    cand_required = set(cand_schema.get("required", []))
    if base_required != cand_required:
        added = sorted(cand_required - base_required)
        removed = sorted(base_required - cand_required)
        detail = f"+{added} -{removed}" if (added or removed) else ""
        drift.append(
            SpecDrift(
                FieldShapeChangeKind.REQUIRED_CHANGED,
                f"components.schemas.{schema_name}",
                detail,
            )
        )

    base_props: dict[str, Any] = base_schema.get("properties", {})
    cand_props: dict[str, Any] = cand_schema.get("properties", {})
    path_prefix = f"components.schemas.{schema_name}"

    for field in sorted(set(base_props) - set(cand_props)):
        drift.append(SpecDrift(FieldShapeChangeKind.FIELD_REMOVED, f"{path_prefix}.{field}"))
    for field in sorted(set(cand_props) - set(base_props)):
        drift.append(SpecDrift(FieldShapeChangeKind.FIELD_ADDED, f"{path_prefix}.{field}"))

    for field in sorted(set(base_props) & set(cand_props)):
        try:
            base_type = _schema_type(baseline, base_props[field])
            cand_type = _schema_type(candidate, cand_props[field])
        except (KeyError, RecursionError):
            continue  # unresolvable ref on either side — not this diff's job to fix
        if base_type != cand_type:
            drift.append(
                SpecDrift(
                    FieldShapeChangeKind.FIELD_TYPE_CHANGED,
                    f"{path_prefix}.{field}",
                    f"{base_type} -> {cand_type}",
                )
            )
    return drift


def diff_site(site: str, refresh: bool = False) -> list[SpecDrift]:
    baseline_path = SPEC_DIR / f"lzt_{site}.json"
    if not baseline_path.exists():
        raise SpecDiffError(f"{site}: no committed baseline at {baseline_path}")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    with TemporaryDirectory(prefix=f"pylzt-spec-diff-{site}-") as tmp_dir:
        tmp_path = Path(tmp_dir) / f"lzt_{site}.json"
        scrape_site(site, tmp_path, refresh=refresh)
        candidate = json.loads(tmp_path.read_text(encoding="utf-8"))

    return diff_specs(baseline, candidate)

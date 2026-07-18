"""Spec-drift diffing — scope: path presence, required-set, per-field type."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dev.codegen.diff import FieldShapeChangeKind, SpecDiffError, diff_site, diff_specs


def _spec(*, paths: dict[str, Any] | None = None, schemas: dict[str, Any] | None = None) -> dict:
    return {
        "openapi": "3.1.0",
        "paths": paths or {},
        "components": {"schemas": schemas or {}},
    }


def test_no_drift_on_identical_specs() -> None:
    spec = _spec(
        paths={"/cart": {"get": {}}},
        schemas={"User": {"required": ["id"], "properties": {"id": {"type": "integer"}}}},
    )
    assert diff_specs(spec, spec) == []


def test_endpoint_added_and_removed() -> None:
    baseline = _spec(paths={"/cart": {"get": {}}, "/old": {"get": {}}})
    candidate = _spec(paths={"/cart": {"get": {}}, "/new": {"get": {}}})
    drift = diff_specs(baseline, candidate)
    kinds = {(d.kind, d.path) for d in drift}
    assert (FieldShapeChangeKind.ENDPOINT_REMOVED, "paths./old") in kinds
    assert (FieldShapeChangeKind.ENDPOINT_ADDED, "paths./new") in kinds


def test_schema_added_and_removed() -> None:
    baseline = _spec(schemas={"Old": {"properties": {}}})
    candidate = _spec(schemas={"New": {"properties": {}}})
    drift = diff_specs(baseline, candidate)
    kinds = {(d.kind, d.path) for d in drift}
    assert (FieldShapeChangeKind.SCHEMA_REMOVED, "components.schemas.Old") in kinds
    assert (FieldShapeChangeKind.SCHEMA_ADDED, "components.schemas.New") in kinds


def test_field_added_and_removed() -> None:
    baseline = _spec(schemas={"User": {"properties": {"id": {"type": "integer"}}}})
    candidate = _spec(schemas={"User": {"properties": {"name": {"type": "string"}}}})
    drift = diff_specs(baseline, candidate)
    kinds = {(d.kind, d.path) for d in drift}
    assert (FieldShapeChangeKind.FIELD_REMOVED, "components.schemas.User.id") in kinds
    assert (FieldShapeChangeKind.FIELD_ADDED, "components.schemas.User.name") in kinds


def test_field_type_changed() -> None:
    baseline = _spec(schemas={"User": {"properties": {"balance": {"type": "string"}}}})
    candidate = _spec(schemas={"User": {"properties": {"balance": {"type": "integer"}}}})
    drift = diff_specs(baseline, candidate)
    assert len(drift) == 1
    assert drift[0].kind is FieldShapeChangeKind.FIELD_TYPE_CHANGED
    assert drift[0].path == "components.schemas.User.balance"


def test_required_set_changed() -> None:
    baseline = _spec(schemas={"User": {"required": ["id"], "properties": {}}})
    candidate = _spec(schemas={"User": {"required": ["id", "email"], "properties": {}}})
    drift = diff_specs(baseline, candidate)
    assert len(drift) == 1
    assert drift[0].kind is FieldShapeChangeKind.REQUIRED_CHANGED


def test_diff_site_raises_on_missing_baseline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("dev.codegen.diff.SPEC_DIR", tmp_path)
    with pytest.raises(SpecDiffError):
        diff_site("antipublic")


def test_diff_site_scrapes_to_tempdir_and_diffs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("dev.codegen.diff.SPEC_DIR", tmp_path)
    baseline = _spec(paths={"/cart": {"get": {}}})
    (tmp_path / "lzt_market.json").write_text(json.dumps(baseline), encoding="utf-8")

    def _fake_scrape_site(site: str, out_path: Path, refresh: bool = False) -> None:
        out_path.write_text(json.dumps(_spec(paths={"/cart": {"get": {}}, "/new": {"get": {}}})))

    monkeypatch.setattr("dev.codegen.diff.scrape_site", _fake_scrape_site)

    drift = diff_site("market")
    assert len(drift) == 1
    assert drift[0].kind is FieldShapeChangeKind.ENDPOINT_ADDED

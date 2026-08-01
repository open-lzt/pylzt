"""`merge_fragment` must not lose an operation, and a shrinking scrape must not be written.

Both guard the same failure mode: the generator emitting a SMALLER SDK with no error anywhere.
That is how `GET /conversations`, `GET /notifications` and `GET /user/payments` disappeared from
the spec — each shares a path with another verb documented on its own page — and then got
hand-written against a guessed response shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dev.codegen.scraper import (
    ScrapeShrank,
    ScrapeStats,
    _operation_count,
    merge_fragment,
)


def _fragment(path: str, verb: str, summary: str) -> dict[str, object]:
    return {
        "openapi": "3.1.0",
        "info": {},
        "servers": [],
        "paths": {path: {verb: {"summary": summary, "responses": {}}}},
    }


def test_two_verbs_on_one_path_both_survive() -> None:
    """The exact shape that lost `GET /conversations` to `POST /conversations`."""
    merged: dict[str, object] = {}
    stats = ScrapeStats()

    merge_fragment(merged, _fragment("/conversations", "get", "list"), stats, "…/list.md")
    merge_fragment(merged, _fragment("/conversations", "post", "create"), stats, "…/create.md")

    paths = merged["paths"]
    assert isinstance(paths, dict)
    assert sorted(paths["/conversations"]) == ["get", "post"]
    assert paths["/conversations"]["get"]["summary"] == "list"
    assert paths["/conversations"]["post"]["summary"] == "create"
    assert stats.operation_conflicts == []


def test_same_verb_twice_with_different_bodies_is_reported_not_silently_dropped() -> None:
    merged: dict[str, object] = {}
    stats = ScrapeStats()

    merge_fragment(merged, _fragment("/conversations", "get", "one"), stats, "…/a.md")
    merge_fragment(merged, _fragment("/conversations", "get", "two"), stats, "…/b.md")

    assert stats.operation_conflicts == ["GET /conversations"]
    assert merged["paths"]["/conversations"]["get"]["summary"] == "one"  # first wins, loudly


def test_each_operation_keeps_its_own_source_url() -> None:
    merged: dict[str, object] = {}
    stats = ScrapeStats()

    merge_fragment(merged, _fragment("/conversations", "get", "list"), stats, "https://x/list.md")
    merge_fragment(merged, _fragment("/conversations", "post", "new"), stats, "https://x/new.md")

    ops = merged["paths"]["/conversations"]
    assert ops["get"]["x-source-url"] == "https://x/list"
    assert ops["post"]["x-source-url"] == "https://x/new"


def test_operation_count_counts_verbs_not_paths() -> None:
    spec = {"paths": {"/a": {"get": {}, "post": {}}, "/b": {"get": {}}}}
    assert _operation_count(spec) == 3


def test_writing_a_smaller_spec_over_a_bigger_one_raises(tmp_path: Path) -> None:
    """A partial scrape is the dangerous case: it has no symptom other than a smaller SDK."""
    from dev.codegen import scraper

    out = tmp_path / "spec.json"
    out.write_text(json.dumps({"paths": {"/a": {"get": {}}, "/b": {"get": {}}}}), encoding="utf-8")

    def _one_page(*args: object, **kwargs: object) -> list[str]:
        return ["https://example/reference/a.md"]

    scraper.list_endpoint_pages = _one_page  # type: ignore[assignment]
    scraper._fetch = lambda *a, **k: ("", True)  # type: ignore[assignment]
    scraper.extract_openapi_fragment = lambda _md: _fragment("/a", "get", "only")  # type: ignore[assignment]

    with pytest.raises(ScrapeShrank):
        scraper.scrape_site("market", out, refresh=False)

    # the old spec is still on disk, untouched
    assert _operation_count(json.loads(out.read_text(encoding="utf-8"))) == 2

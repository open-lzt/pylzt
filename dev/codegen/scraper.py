"""Scrape the official lzt-market/lolzteam readme.io API references and merge the
per-endpoint OpenAPI 3.1 fragments embedded in each page into one spec per site.

Each `https://<site>.readme.io/reference/<slug>.md` page embeds a fenced ```json
code block under a "# OpenAPI definition" heading — a self-contained OpenAPI
document covering just that one path. This script fetches every page listed in
the site's `llms.txt` index, extracts that fragment, and unions the `paths` and
`components.*` across all pages into a single merged spec.

Usage (normally driven by the pipeline — `python -m dev.codegen scrape`):
    python -m dev.codegen.scraper --site market --out dev/generated/openapi/lzt_market.json
    python -m dev.codegen.scraper --site forum --out dev/generated/openapi/lzt_forum.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SITES = {
    "market": "https://lzt-market.readme.io",
    "forum": "https://lolzteam.readme.io",
    "antipublic": "https://antipublic.readme.io",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

PAGE_URL_RE = re.compile(
    r"\]\((https://[a-z0-9.-]+readme\.io/reference/[a-z0-9_-]+)\.md\)", re.IGNORECASE
)
JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)

REQUEST_DELAY_SECONDS = 1.5
MAX_RETRIES = 5


@dataclass
class ScrapeStats:
    """Counts surfaced to the operator after a run — not a domain object."""

    total_pages: int = 0
    fetched: int = 0
    with_openapi_fragment: int = 0
    failed: list[str] = field(default_factory=list)
    component_conflicts: list[str] = field(default_factory=list)
    #: `"GET /conversations"` entries where two doc pages defined the same path AND the same
    #: verb with different bodies. A path shared by DIFFERENT verbs is normal and merges
    #: quietly; only a genuine verb-level clash lands here.
    operation_conflicts: list[str] = field(default_factory=list)


def _cache_key(url: str) -> str:
    m = re.search(r"/reference/([a-z0-9_-]+)", url, re.IGNORECASE)
    return m.group(1) if m else re.sub(r"[^A-Za-z0-9]+", "_", url).strip("_")


def _fetch(url: str, cache_dir: Path | None = None, refresh: bool = False) -> tuple[str, bool]:
    """Return (markdown, from_cache). Each page is cached on disk by its readme.io slug so a
    re-scrape reuses it instead of re-hitting the network; `refresh=True` forces a refetch and
    rewrites the cache."""
    cache_file = cache_dir / f"{_cache_key(url)}.md" if cache_dir else None
    if cache_file is not None and not refresh and cache_file.exists():
        return cache_file.read_text(encoding="utf-8"), True

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/markdown"})
    delay = REQUEST_DELAY_SECONDS
    text: str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    if text is None:
        raise RuntimeError(f"unreachable: retries exhausted for {url}")
    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8")
    return text, False


def list_endpoint_pages(
    site_base: str, cache_dir: Path | None = None, refresh: bool = False
) -> list[str]:
    text, _ = _fetch(f"{site_base}/llms.txt", cache_dir, refresh)
    urls = {m.group(1) + ".md" for m in PAGE_URL_RE.finditer(text)}
    return sorted(urls)


def extract_openapi_fragment(markdown: str) -> dict[str, Any] | None:
    m = JSON_FENCE_RE.search(markdown)
    if m is None:
        return None
    return json.loads(m.group(1))


def merge_fragment(
    merged: dict[str, Any], fragment: dict[str, Any], stats: ScrapeStats, page_url: str
) -> None:
    if "openapi" not in merged:
        merged["openapi"] = fragment.get("openapi", "3.1.0")
        merged["info"] = fragment.get("info", {})
        merged["servers"] = fragment.get("servers", [])
        merged["paths"] = {}
        merged["components"] = {}

    # Tag each operation with its source doc page so codegen can link back to it.
    doc_url = page_url[:-3] if page_url.endswith(".md") else page_url
    for methods in fragment.get("paths", {}).values():
        for op in methods.values():
            if isinstance(op, dict):
                op["x-source-url"] = doc_url
    # Merge PER VERB, not per path: one doc page per operation means `GET /conversations` and
    # `POST /conversations` arrive separately, and a path-level `update` silently dropped
    # whichever verb was scraped first.
    for path, methods in fragment.get("paths", {}).items():
        target = merged["paths"].setdefault(path, {})
        for verb, op in methods.items():
            existing = target.get(verb)
            if existing is not None and existing != op:
                stats.operation_conflicts.append(f"{verb.upper()} {path}")
                continue
            target[verb] = op

    for comp_kind, comp_map in fragment.get("components", {}).items():
        bucket = merged["components"].setdefault(comp_kind, {})
        for name, defn in comp_map.items():
            existing = bucket.get(name)
            if existing is not None and existing != defn:
                stats.component_conflicts.append(f"components.{comp_kind}.{name}")
                continue
            bucket[name] = defn


class ScrapeShrank(RuntimeError):
    """A run produced fewer operations than the spec it was about to overwrite."""

    def __init__(self, site: str, before: int, after: int) -> None:
        super().__init__(
            f"[{site}] scrape produced {after} operations, previous spec had {before}. "
            "Refusing to overwrite — a partial scrape (docs reshuffled, a selector broken, "
            "pages 404ing) shrinks the generated SDK with no other symptom. "
            "Re-run with --allow-shrink once the drop is understood."
        )


def _operation_count(spec: dict[str, Any]) -> int:
    return sum(len(methods) for methods in spec.get("paths", {}).values())


def scrape_site(
    site: str, out_path: Path, refresh: bool = False, allow_shrink: bool = False
) -> ScrapeStats:
    site_base = SITES[site]
    stats = ScrapeStats()
    cache_dir = out_path.parent / ".page_cache" / site

    pages = list_endpoint_pages(site_base, cache_dir, refresh)
    stats.total_pages = len(pages)
    print(f"[{site}] {len(pages)} endpoint pages found", file=sys.stderr)

    merged: dict[str, Any] = {}
    for i, url in enumerate(pages, 1):
        try:
            markdown, from_cache = _fetch(url, cache_dir, refresh)
            stats.fetched += 1
        except Exception as e:
            stats.failed.append(f"{url}: {e}")
            print(f"[{site}] {i}/{len(pages)} FAILED {url}: {e}", file=sys.stderr)
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        fragment = extract_openapi_fragment(markdown)
        if fragment is None:
            stats.failed.append(f"{url}: no OpenAPI fragment found on page")
            print(f"[{site}] {i}/{len(pages)} no fragment {url}", file=sys.stderr)
        else:
            stats.with_openapi_fragment += 1
            merge_fragment(merged, fragment, stats, url)
            tag = "cached" if from_cache else "ok"
            print(f"[{site}] {i}/{len(pages)} {tag} {url}", file=sys.stderr)

        if not from_cache:  # only throttle real network hits
            time.sleep(REQUEST_DELAY_SECONDS)

    # The floor. A run that returns nothing is already caught downstream ("nothing staged"),
    # but a PARTIAL miss was caught by nothing at all: it just wrote a smaller spec, and the
    # next build quietly emitted a smaller SDK.
    after = _operation_count(merged)
    if out_path.exists():
        previous = json.loads(out_path.read_text(encoding="utf-8"))
        before = _operation_count(previous)
        if after < before and not allow_shrink:
            raise ScrapeShrank(site, before, after)
    elif after == 0:
        raise ScrapeShrank(site, 0, 0)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", choices=sorted(SITES), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true", help="ignore the page cache and refetch")
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help="write the spec even if it holds fewer operations than the one it replaces",
    )
    args = parser.parse_args()

    stats = scrape_site(args.site, args.out, refresh=args.refresh, allow_shrink=args.allow_shrink)

    print(f"\n=== {args.site} ===", file=sys.stderr)
    print(
        f"pages: {stats.total_pages}, fetched: {stats.fetched}, "
        f"with openapi fragment: {stats.with_openapi_fragment}",
        file=sys.stderr,
    )
    if stats.failed:
        print(f"failed ({len(stats.failed)}):", file=sys.stderr)
        for f in stats.failed:
            print(f"  - {f}", file=sys.stderr)
    if stats.component_conflicts:
        print(f"component conflicts ({len(stats.component_conflicts)}):", file=sys.stderr)
        for c in sorted(set(stats.component_conflicts)):
            print(f"  - {c}", file=sys.stderr)
    print(f"written: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

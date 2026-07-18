# spec-drift-ci-checker

**Goal**: CLI (`python -m dev.codegen diff`) re-scrapes a fresh readme.io fragment
per API site, diffs it against the committed `dev/generated/openapi/lzt_*.json`,
exits non-zero on a field-shape change (endpoint/schema added-removed, field
added-removed, type changed, required changed) — catches upstream API drift
before a bug report does.

**Touch**:
- `dev/codegen/diff.py` — **new**.
- `dev/codegen/__main__.py` — add `diff` subcommand (if/elif dispatch, matches
  existing `generate`/`install`/`build`/`scrape`/`check` convention).
- `.github/workflows/ci.yml` — optional `+1` step calling the new subcommand
  (include only if cheap; skip if it'd need new secrets/network policy).

**Contracts/Types**:
```python
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
    path: str     # "paths./market/cart.get" | "components.schemas.User.balance"
    detail: str   # e.g. "str -> int"; empty for add/remove kinds

class SpecDiffError(CodegenError):
    def __init__(self, api: str, reason: str) -> None: ...

def diff_specs(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[SpecDrift]: ...
def diff_site(site: str, refresh: bool = False) -> list[SpecDrift]: ...
```

**Approach**:
1. `diff_specs()` compares two OpenAPI 3.1 dicts scoped to: path presence,
   per-schema required-field set, per-field resolved type (reuse
   `generator.py`'s `_schema_type`/`_resolve_ref`, don't re-derive). No
   description/example/summary diffing (out of scope).
2. `diff_site()` calls `scraper.scrape_site(site, tmp_path, refresh)` against a
   **tempfile** (confirmed: `scrape_site` always writes, no in-memory variant —
   never point it at the committed path), loads both JSONs, diffs, cleans up
   tempfile in `finally`.
3. `antipublic` has no committed baseline → `diff_site` raises
   `SpecDiffError(site, "no committed baseline")`, not `FileNotFoundError`.
4. `__main__.py`: new `diff` subparser (`_add_api` convention), prints one
   line per `SpecDrift`, exit 1 if any found else 0 — matches `check`'s
   plain-stdout/exit-code convention, no new report wrapper type.

**Risk/edge**: network flakiness during CI scrape — rely on `scraper.py`'s
existing `MAX_RETRIES=5`, no second retry layer. `CodegenError` subclassing
uses this module's bare-message convention (not args-carrying) — matches
existing `CodegenError`, don't force the stricter global rule in isolation.

**Test**: `diff_specs()` unit tests (added field, removed field, type change,
required change, added/removed endpoint, no-op on identical specs);
`diff_site()` integration test with a fake `scrape_site` swap-in.

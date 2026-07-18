# dev/codegen

The pylzt code generator: turn the official readme.io OpenAPI reference into typed
`BaseMethod[T]` methods, Pydantic response models, `StrEnum`s and `Client` facades, and
install them **flat** into the library behind a ruff + mypy gate.

## Two phases (entrypoint: `python -m dev.codegen`)

- **`generate`** — render the SDK into the flat STAGING tree `dev/codegen/generated/`
  (`methods/`, `models/`, `enums/`, `facades/`). Reads the library to dedup against
  hand-written methods, but never writes to it. `--api`, `--scrape`, `--model-backend`.
- **`install`** — promote the staged files flat into `src/pylzt/{methods,models,enums,facades}/`
  behind the gate (ruff + mypy strict + import smoke), atomically. `--no-validate` to skip.
- **`build`** — `generate` + `install` in one shot.
- **`scrape`** — scrape + merge the OpenAPI spec into `dev/generated/openapi/lzt_<site>.json`.
- **`check`** — run the gate over `src/pylzt` without regenerating.

## Files

- `pipeline.py` — orchestration. `install()` refuses to overwrite hand-written modules,
  snapshots the currently-installed generated files, wipes them (so a removed domain's file
  disappears), copies the staged set in, ruff-fixes, runs the gate, and on failure restores
  the snapshot.
- `generator.py` — the OpenAPI → Python renderer (`generate_all`, model/enum/facade builders).
  Facade methods carry the same full docstring as their method class (`_format_docstring`,
  indent-parameterized). Nested model names are bounded to two PascalCase segments
  (`RenderedAvatars`, not the full ancestry) and identifier-sanitised (`_safe_type_name`).
  A wire object whose keys are all dynamic (UUIDs / integer indices / long hex — `_DYNAMIC_KEY`)
  is a MAP the spec encoded with example keys → rendered `dict[str, V]`, never a model with a
  field named after the example key.
  A post-build normalisation pass (`_collapse_models`) then: **(Rule 1)** folds a family of
  models with identical field NAMES that differ only in some fields' TYPES into one PEP-695
  generic base (`CategoryResponse[CategoryResponseItemT]`), renaming each opaque type-arg model
  from `Item6` to `<discriminator><FieldLeaf>` (`FortniteItem`); **(Rule 2)** for each known
  generic type-arg family, hoists the shared leading run of identical fields into a synthesized
  `Base<Stem>` (`BaseItem`) and reduces each member to a subclass of it. Every reference (op
  return types, `__returning__`, field annotations) is rewritten to the parametrized/renamed
  form. Runs for the pydantic backend only. Model dedup is order-insensitive (the same field
  set in a different order reuses one class), collisions disambiguate by owning-response context
  (`UsersGetUser`, not `User2`) rather than a numeric suffix, and a response shape shared by ≥2
  operations gets a neutral field-derived name (`{status, message}` → `StatusMessageResponse`,
  not the first operation's name) — folding into a generic (`StatusItemResponse[T]`) when such
  shapes differ only by a field type. Invariant: no generated model name carries a numeric
  disambiguation suffix. Generated facade methods run via the client's `__call__`
  (`self(Method(...))`), and `install` runs `ruff format` so long signatures wrap (PEP 8).
  A response root that is an object with exactly one field (after the `system_info` filter) is
  unwrapped — the method returns that field's type directly (`{tags: [Tag]}` → `list[Tag]`) via
  `__returning__ = <item model>` + `__unwrap__ = <key>`, so no one-field wrapper model is emitted.
  `_enum_from_schema` collapses any per-field enum whose wire values are a subset of
  `{yes, no, nomatter}` onto the one hand-written `Tristate` (`pylzt.types`, with a
  `from_bool` classmethod) instead of emitting a same-shaped duplicate class per field name
  (`Tel`, `EditBtag`, `ClashPass`, ...). `_rebase_status_responses` rebases any model whose
  leading field is `status: str` onto the hand-written `BaseResponse` (`pylzt.models.base`,
  owns `is_ok()`) and drops the now-inherited field.
- `scraper.py` — fetches every readme.io reference page and unions the embedded OpenAPI 3.1
  fragments into one spec. Each page is cached on disk by its readme.io slug under
  `dev/generated/openapi/.page_cache/<site>/` (gitignored with the rest of `dev/generated/`), so
  a re-scrape reuses pages instead of re-hitting the network and skips the per-page throttle on
  cache hits. Pass `--refresh` (on `scrape` / `generate --scrape` / `build --scrape`) to ignore
  the cache and refetch.

## Contracts

- Generated and hand-written modules coexist **flat** in the same package. They're told apart
  two ways: (1) every generated file carries the `GEN_MARKER` string in its header; (2) a
  naming invariant — **hand-written modules are unprefixed** (`catalog.py`, `conversations.py`),
  **generated ones always carry an `{api}_` prefix or an `{api}` name** (`market_cart.py`,
  `forum_conversations.py`, `models/market.py`).
- **`install` never overwrites a hand-written module.** `_guard_no_clobber` drops (warns,
  excludes) any staged file whose target exists and lacks the marker — the "builder works
  always" guarantee. A clash means a generated domain collided with curated code; that one
  file is skipped but the rest of the batch still installs, and `install()` reports
  installed-vs-skipped counts.
- Install is all-or-nothing: on any gate failure the previous generated files are restored, so
  the library on disk is never left broken by a regen.
- Facade names never shadow hand-written `Client` methods (`_client_method_names()` seeds the
  taken-name pool); endpoint dedup is path-placeholder-normalized, and skips marker-carrying
  files so it dedups only against curated methods.

## Gotchas

- The gate runs `python -m {ruff,mypy}` via `sys.executable` — the interpreter that runs the
  pipeline must have `ruff`, `mypy` and an editable `pylzt` install (the `[dev]` extra).
- The generator emits imports in declaration order; ruff owns their final sort. `install`
  runs `ruff check --fix` on the just-installed files before the gate, so import ordering
  (`I001`) never fails it. If ruff still flags import order in an UNPREFIXED file, that's a
  hand-written edit you made — fix it.
- The staging tree `dev/codegen/generated/` is gitignored and wiped on every `generate`.
- Run from the repo root so `python -m dev.codegen` resolves (`dev` is a namespace package).

## See also

- `../../README.md` — Codegen section.
- `../../src/pylzt/methods/base.py` — the `BaseMethod[T]` contract the skeletons target.

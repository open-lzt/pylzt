# Files — api-namespaces

| File | Change |
|---|---|
| `src/pylzt/types.py` | Add `ApiTarget.ANTIPUBLIC`, `RateClass.ANTIPUBLIC` |
| `src/pylzt/config.py` | Add `antipublic_base_url`, `antipublic_per_min` fields |
| `dev/codegen/scraper.py` | Add `"antipublic"` to `SITES` dict (line 28-31) |
| `dev/codegen/generator.py` | Extend `--api` choices + `render_method_skeleton` `api == "antipublic"` branch (mirrors the existing forum branch at line 675) |
| `dev/codegen/pipeline.py` | Add `"antipublic"` to `APIS` tuple (line 35) |
| `src/pylzt/facades/antipublic.py` | **Generated** by running `python -m dev.codegen build --scrape --api antipublic` (task T4) — not hand-written |
| `src/pylzt/models/antipublic/*.py` | **Generated** alongside the facade — 9 endpoints' response models |
| `src/pylzt/facades/_namespace.py` | **New, hand-written** — `_Namespace` base + `MarketNamespace`/`ForumNamespace`/`AntipublicNamespace` |
| `src/pylzt/token_pool/_static.py` | **New, hand-written** — `_StaticBearerPool`, a minimal single-credential `BaseTokenPool` impl for AntiPublic (see 03-types.md) |
| `src/pylzt/client.py` | Remove `GeneratedMarketFacade, GeneratedForumFacade` mixin bases; add `antipublic_key`/`antipublic_transport` params; construct namespaces in `__init__`; move `get_lot`/`get_lots_batch`/`list_lots`/`list_categories`/`category_params`/`category_games` onto `MarketNamespace` |
| `src/pylzt/__init__.py` | Update `__all__`/re-exports if `MarketNamespace`/`ForumNamespace`/`AntipublicNamespace` become part of the stable public surface (they're referenced as `client.market`'s type, so yes) |
| `README.md`, `docs/integration-guide.md` | Update every code example from `client.<method>()` to `client.market.<method>()` / `client.forum.<method>()` |
| `tests/pylzt/*.py` (multiple) | Update call sites that construct/call through the old flat facade |
| `tests/pylzt/e2e/test_live_read.py` | Update `_discover_get_methods` (currently scans `pylzt.methods` package directly — unaffected by facade attachment, only the manual chain tests' call sites like `client.forums_list()` need updating to `client.forum.forums_list()`) |

## Cross-file interactions

- `_namespace.py` imports all 3 generated facades — created only after T4 (codegen run)
  produces `facades/antipublic.py`, so `_namespace.py`'s `AntipublicNamespace` cannot be
  written before T4 completes (see DAG in 04-tasks.yaml: T5 depends_on T4).
- `client.py`'s import of `GeneratedMarketFacade`/`GeneratedForumFacade` moves from
  "base class" usage to "imported only inside `_namespace.py`" — `client.py` itself no
  longer imports them directly once T6 lands.

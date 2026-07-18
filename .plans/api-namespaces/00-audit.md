# Audit — api-namespaces

Solo collapse (module tier, no parallel research agents). Findings from reading
`client.py`, `facades/market.py`/`forum.py`, `config.py`, `types.py`,
`dev/codegen/{scraper,generator,pipeline}.py`.

## Existing patterns

- **Mixin-inheritance facade attachment**: `class Client(GeneratedMarketFacade,
  GeneratedForumFacade)` — every generated method becomes a `Client` instance method via
  Python MRO. `follow`-able for the *shape* of individual facade classes (plain class,
  `async def`, calls `self.execute(...)`) — only the *attachment* mechanism changes.
- **`__api__`/`__rate_class__` injection is already per-site in codegen**
  (`generator.py:675`, `render_method_skeleton`, forum branch) — the pattern this plan
  extends to a 3rd branch is already established, not invented fresh.
- **`SITES` dict (scraper.py:28-31) and `APIS` tuple (pipeline.py:35) are the single
  source of truth for "which sites codegen knows about"** — both are flat, additive;
  adding `"antipublic"` is a 1-line change to each, no restructuring needed.
- **Client already runs 2 independent `RateLimitedTransport` instances sharing one
  `token_pool`** (`self._transport`, `self._forum_transport`) — the pattern for
  AntiPublic's 3rd transport is a straightforward 3rd instance, not a new mechanism.

## Inconsistencies / anti-patterns found

- **`Client` docstring says "composition root, not an extension point"** but the current
  mixin-inheritance (`Client(GeneratedMarketFacade, GeneratedForumFacade)`) IS an
  inheritance-based extension, contradicting its own stated design intent. `fix` — this
  plan's namespace-composition approach actually resolves this pre-existing contradiction
  as a side effect, not just adds namespaces.
- **`ClientConfig` is a flat dataclass with per-site fields prefixed ad hoc**
  (`base_url` for market with no prefix, `forum_base_url` for forum) — adding a 3rd
  `antipublic_base_url` continues an already-inconsistent naming scheme (market has no
  prefix, forum/antipublic do). `defer` — renaming `base_url` → `market_base_url` is a
  separate breaking change with its own blast radius (every existing config construction
  site); out of scope here, logged for a future config-cleanup plan.

## Tech debt in blast radius

| ID | Finding | Where | Cost | Decision |
|---|---|---|---|---|
| TD-1 | `Client` mixin-inheritance contradicts its own "composition root" docstring | `client.py:71` | M (this plan fixes it as a side effect) | must-include |
| TD-2 | `ClientConfig` per-site field naming inconsistent (`base_url` vs `forum_base_url`) | `config.py` | M (separate blast radius) | defer |

## Analogous features

- **Forum's own `ApiTarget`/`RateClass`/transport addition** (a past commit, not
  identified by hash here but visible in the current shape of `client.py`/`config.py`/
  `types.py`) is the direct precedent this plan's AntiPublic addition mirrors 1:1.

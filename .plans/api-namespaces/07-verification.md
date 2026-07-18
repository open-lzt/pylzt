# W3.5 code-grounded verification — api-namespaces

Two Sonnet audit agents, fan-out (module tier mandatory). Part A: `client.py` +
facades + hand-written-method migration risk. Part B: `token_pool` + `transport` +
`errors` + `__init__.py` + `config.py`.

## 🔴 Blocker (fixed — see below)

**`_Namespace`'s original contract only delegated `execute()`, not `__call__()`.**
Every one of the ~190 generated market/forum methods calls `self(SomeMethod(...))` —
`__call__` — never `self.execute(...)` directly (`facades/market.py`: 89/89 methods
verified, `facades/forum.py`: 101/101 methods verified). `GeneratedMarketFacade`/
`GeneratedForumFacade` only declare `__call__` under `if TYPE_CHECKING:` — a
type-checker-only stub, not a runtime method; today it works purely because `Client`
provides `__call__` (client.py:333-335) and mixin inheritance puts `Client` in the MRO.

**As originally specified, this refactor would have broken 100% of generated methods**
with `TypeError: 'MarketNamespace' object is not callable` the moment it shipped.

**Fixed**: `00-overview.md`'s `_Namespace` now delegates both `execute()` and
`__call__()`. `04-tasks.yaml` T5's acceptance now explicitly tests `__call__`
delegation, not just `.execute()`.

## 🟡 Corrections (folded in)

1. **`_rate_limited(self, transport)` hard-codes `self._token_pool`** (client.py) —
   needs a `pool` parameter for the antipublic leg to pass `_StaticBearerPool` instead
   of the shared pool. Folded into T6.
2. **`_transport_for` is a binary MARKET-vs-else branch**, not a 3-way match — anything
   non-MARKET today silently falls to `_forum_transport`; harmless while only 2 targets
   exist, but must become a real match once `ApiTarget.ANTIPUBLIC` exists. Folded into T6.
3. **`self.config`/`self._category_cache` accesses in `list_lots`/`category_params`**
   (2 methods, 4 access sites total) must become `self._client.config`/
   `self._client._category_cache` after the T7 move to `MarketNamespace`. Folded into T7.
4. **`_StaticBearerPool` should NOT literally reuse `RoundRobinTokenPool`/
   `RateBucketSet.standard()`** — that shape is hardcoded to 3 named rate classes +
   multi-token selector rotation, neither of which a single-credential pool needs.
   Reworded from "mirrors"/"reuses" to "algorithm-inspired, standalone reimplementation"
   in `03-types.md` and T2's acceptance.
5. **`DependencyMissing` is a bad semantic fit for "AntiPublic key not configured"** —
   its only real call site (`transport/session.py:112`) and docstring are scoped to
   "optional pip package not installed"; reusing it for a missing credential would
   misleadingly suggest `pip install antipublic_key`. Replaced with a new
   `CredentialMissing(credential: str)` error class (`errors.py`, <10 LOC) in
   `03-types.md`, `04-tasks.yaml` T6, and `05-risks.md` R2.
6. **R4's `__all__` assumption reversed**: `__init__.py`'s current 66-entry `__all__`
   exports **neither** `GeneratedMarketFacade` nor `GeneratedForumFacade` today — no
   facade type has ever been part of the public surface. So R4 originally argued
   *for* exporting the new namespace classes based on a precedent that doesn't
   actually exist; revised to make T8's non-export the explicit default, confirmed
   against observed practice, not the docstring's aspirational statement.

## Verdict

No unresolved 🔴 blockers after the fixes above (the one blocker found is fixed in the
plan text). Plan is implementation-ready pending user approval. `validate_plan.py`
re-run after all corrections: see Present message.

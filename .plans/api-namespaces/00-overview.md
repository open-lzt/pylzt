# API namespaces — overview

**Tier:** module (full pipeline, solo-collapsed) — justified by: breaking public-API
change pre-release + a brand-new external API integration (AntiPublic) whose contract
was unknown until scraped this session + a codegen architecture change (facade
attachment). **Mode:** layered, solo, one pass with mandatory W3.5 code-verify.
**Slug:** `api-namespaces` · root: `.plans/api-namespaces/`

## Goal

Replace the current flat facade (`Client(GeneratedMarketFacade, GeneratedForumFacade)` —
~200 methods mixed directly onto `Client`) with exactly 3 top-level domain namespaces:
`client.market.*`, `client.forum.*`, `client.antipublic.*`. Stand up AntiPublic
(`antipublic.one/api/v2`, leak-checking API, 9 endpoints, separate Bearer license key) as
a third API target from scratch — it does not exist in any form today (no `ApiTarget`
member, no spec, no facade).

## Scope

1. **`types.py`** — `ApiTarget.ANTIPUBLIC = "antipublic"`, `RateClass.ANTIPUBLIC = "antipublic"`.
2. **`config.py`** — `ClientConfig.antipublic_base_url: str = "https://antipublic.one/api/v2"`,
   `antipublic_per_min: int` (default TBD from live `/checkAccess` response — see Risks).
3. **`dev/codegen/scraper.py`** — add `"antipublic": "https://antipublic.readme.io"` to
   `SITES` (scraper.py:28-31).
4. **`dev/codegen/generator.py`** — extend `--api` CLI choices to include `"antipublic"`
   (generator.py:1511); extend the forum-style `__api__`/`__rate_class__` injection in
   `render_method_skeleton` (generator.py:675) to also handle `api == "antipublic"`.
5. **`dev/codegen/pipeline.py`** — add `"antipublic"` to `APIS = ("market", "forum")`
   (pipeline.py:35) so `python -m dev.codegen build` covers all 3 sites.
6. **Run codegen** — `python -m dev.codegen build --scrape --api antipublic` to produce
   `facades/antipublic.py` (`GeneratedAntipublicFacade`) + the 9 AntiPublic response
   models + methods, same shape as the existing market/forum generation.
7. **New: `src/pylzt/facades/_namespace.py`** — 3 thin namespace wrapper classes
   (`MarketNamespace`, `ForumNamespace`, `AntipublicNamespace`), each `(GeneratedXFacade)`
   holding a `_client: Client` reference and overriding **both `execute()` AND
   `__call__()`** to delegate — see Key types below. **CORRECTED (W3.5 finding, was
   originally wrong)**: generated facade method bodies call `self(SomeMethod(...))` —
   i.e. `__call__` — never `self.execute(...)` directly; `GeneratedMarketFacade`/
   `GeneratedForumFacade` only declare `__call__` under `if TYPE_CHECKING:` (a stub, not
   a runtime method) — today it works purely because `Client` itself provides `__call__`
   and mixin inheritance puts `Client` in the MRO. `_Namespace` must therefore delegate
   `__call__` too, or all ~190 generated methods break with `TypeError: not callable`.
   With that fix in place, the generated method bodies themselves genuinely need zero
   changes — the delegation happens one level up, in `_Namespace`.
8. **`client.py`** — drop the `GeneratedMarketFacade, GeneratedForumFacade` base classes
   from `Client`; construct `self.market = MarketNamespace(self)`,
   `self.forum = ForumNamespace(self)`, `self.antipublic = AntipublicNamespace(self)` in
   `__init__`. Move the hand-written market-domain convenience methods
   (`get_lot`, `get_lots_batch`, `list_lots`, `list_categories`, `category_params`,
   `category_games`) onto `MarketNamespace` too (they're market-domain, for the same
   reason the generated market methods live there — see Decisions); **W3.5 confirmed**
   `list_lots`/`category_params` reach `self.config`/`self._category_cache` (Client-level
   attrs) — these become `self._client.config`/`self._client._category_cache` after the
   move (`self.execute` itself needs no rewrite, `_Namespace.execute` covers it).
   `execute`, `__call__`, `reconfigure`, `aclose`, `execute_batch`, and the batch-job-
   history methods stay top-level on `Client` (cross-cutting/transport concerns, not
   domain-specific). **W3.5 also found `_rate_limited(self, transport)` hard-codes
   `self._token_pool`** — must be parametrized to `_rate_limited(self, transport, pool)`
   so the antipublic leg can pass `_StaticBearerPool` instead; and **`_transport_for`
   is currently a binary MARKET-vs-else branch** — must become a genuine 3-way match on
   `ApiTarget` (today anything non-MARKET silently falls to `_forum_transport`, which
   would misroute antipublic methods).
9. **`Client.__init__`** gains `antipublic_key: str | None = None` (separate credential,
   never merged into `tokens`/`token_pool` — see Decisions).
10. **New: sync facade generation** — see "Sync wrappers" section below (added at the
    user's request, same generator.py/facade architecture this plan already touches).

## Non-goals

- No AS7-style deep nesting (`market.managing.steam.*`) — flat methods within each of the
  3 namespaces, exactly as they are today, just regrouped.
- No backward-compat shim / deprecation alias for the old flat `client.<method>()` call
  style — the library is **not yet published to PyPI** (confirmed earlier this session),
  so a hard breaking change costs nothing extra right now. Revisit if this plan lands
  after a first release.
- No change to `BaseMethod`/`build_request`/`parse_response` — this plan is purely about
  facade attachment and a new API target, not the method-execution machinery.

## Key types (frozen contract)

```python
# src/pylzt/facades/_namespace.py (new)
from __future__ import annotations
from typing import TYPE_CHECKING, Any
from pylzt.facades.market import GeneratedMarketFacade
from pylzt.facades.forum import GeneratedForumFacade
from pylzt.facades.antipublic import GeneratedAntipublicFacade
from pylzt.methods.base import BaseMethod

if TYPE_CHECKING:
    from pylzt.client import Client

class _Namespace:
    """Shared delegation base: generated facade method bodies call `self(...)`
    (`__call__`) — confirmed by W3.5 code audit, not `self.execute(...)` as first
    assumed — so both must delegate to the owning Client for composition (not the old
    mixin-inheritance) to work at all."""
    def __init__(self, client: "Client") -> None:
        self._client = client

    async def execute[T](self, method: BaseMethod[T]) -> T:
        return await self._client.execute(method)

    async def __call__[T](self, method: BaseMethod[T]) -> T:
        """REQUIRED, not optional (W3.5 finding): every generated facade method body
        calls `self(SomeMethod(...))` — i.e. `__call__` — never `self.execute(...)`
        directly. `GeneratedMarketFacade`/`GeneratedForumFacade` only declare `__call__`
        under `if TYPE_CHECKING:` (a type-checker-only stub); at runtime it's provided
        exclusively by `Client.__call__` today via mixin inheritance. Without this
        override, ALL ~190 generated methods raise `TypeError: 'MarketNamespace' object
        is not callable` the moment this refactor ships — this is the design's real
        cost-saver, not `execute()` alone."""
        return await self._client.execute(method)

class MarketNamespace(_Namespace, GeneratedMarketFacade):
    ...  # + get_lot/get_lots_batch/list_lots/list_categories/category_params/category_games

class ForumNamespace(_Namespace, GeneratedForumFacade):
    ...

class AntipublicNamespace(_Namespace, GeneratedAntipublicFacade):
    ...
```

```python
# client.py — Client.__init__ signature delta (additive + one removal)
def __init__(
    self,
    tokens: Sequence[str | Token] | None = None,
    *,
    antipublic_key: str | None = None,   # NEW — separate credential, see Decisions
    transport: BaseTransport | None = None,
    forum_transport: BaseTransport | None = None,
    antipublic_transport: BaseTransport | None = None,  # NEW — 3rd rate-limited transport
    token_pool: BaseTokenPool | None = None,
    proxy_source: BaseProxySource | None = None,
    retry: BaseRetryPolicy | None = None,
    metrics: BaseMetrics | None = None,
    clock: Clock | None = None,
    category_cache: BaseCache[FilterSchema] | None = None,
    batch_storage: BaseStorage | None = None,
    config: ClientConfig | None = None,
) -> None: ...
# Client(GeneratedMarketFacade, GeneratedForumFacade) mixin bases REMOVED — Client becomes
# a plain composition root again, matching its own docstring ("composition root, not an
# extension point") more literally than the current mixin-inheritance did.
```

```python
# types.py additions
class ApiTarget(StrEnum):
    MARKET = "market"
    FORUM = "forum"
    ANTIPUBLIC = "antipublic"   # NEW

class RateClass(StrEnum):
    GENERAL = "general"
    SEARCH = "search"
    FORUM = "forum"
    ANTIPUBLIC = "antipublic"   # NEW
```

## Decisions (autonomous, tagged)

- **AntiPublic gets its own `antipublic_key` constructor param, never merged into
  `tokens`/`token_pool`.** `verified-by-code:src/pylzt/token_pool/round_robin.py` (the
  existing pool's round-robin selection assumes every token is fungible for the SAME
  market+forum OAuth scope; mixing in a structurally different AntiPublic license key
  risks a round-robin cycle sending it to `antipublic.one` never happening or, worse, an
  OAuth token accidentally landing on an AntiPublic request). **User-confirmed this
  session** (AskUserQuestion, "Отдельный параметр antipublic_key").
- **Namespace holds a `Client` reference (composition), not mixin-inheritance-of-Client.**
  **User-confirmed this session** (AskUserQuestion, "Namespace держит ссылку на Client").
  Consequence: `Client.execute`/`__call__` signatures are completely unchanged — only
  `Client.__init__`'s composition and the facade attachment mechanism change.
- **Hand-written market convenience methods move to `client.market.*` alongside the
  generated ones** — `unverified` (reasonable-default judgment call, not verified against
  an external source): leaving `get_lot`/`list_lots`/etc. on bare `Client` while
  `forums_list`-style generated methods move to `client.forum.*` would produce an
  inconsistent surface (some market operations namespaced, some not). If the user prefers
  keeping the hand-written surface un-namespaced for ergonomics, that's a 1-line change to
  Task T7 flagged here for review.
- **`AntipublicNamespace` gets its own `RateLimitedTransport` + its own `RateClass`,
  mirroring how Forum already gets its own transport/bucket alongside Market** —
  `verified-by-code:src/pylzt/client.py` (`self._transport`/`self._forum_transport` both
  wrap the shared `token_pool` but hit different hosts/buckets; AntiPublic needs the same
  shape, but with `antipublic_key` instead of the shared pool since it isn't fungible with
  market/forum tokens per the decision above).
- **`antipublic_per_min` default is a placeholder pending a live check** — AntiPublic's
  docs state the limit is "simultaneous connections", not requests/min (unlike Market's
  documented 120/min), so the existing `RoundRobinTokenPool` per-minute bucket model may
  not even be the right shape for this target. Flagged as a 🟡 in Risks — needs a live
  `/checkAccess` call to read the real limit shape before this ships, not a guess.

## Sync wrappers (added at user request)

Pyrogram's "sync mode" (a single call that monkey-patches every async method to run
synchronously) breaks static typing — every method's return type becomes ambiguous to
a type checker. Codegen-generated sync facades avoid this: each async method gets a
real, separately-typed synchronous counterpart, generated alongside the async one, no
runtime patching.

**Design** — a persistent background-thread event loop (not `asyncio.run()` per call,
which would raise `RuntimeError` if invoked from inside an already-running loop; the
background-thread approach sidesteps that entirely, matching how other sync-over-async
wrapper libraries do this):

```python
# src/pylzt/sync/runner.py (new)
class SyncRunner:
    """Owns a background event loop thread. run() executes a coroutine via
    asyncio.run_coroutine_threadsafe + Future.result() — works even when called from
    inside a caller's own running event loop, unlike asyncio.run()."""
    def __init__(self) -> None: ...          # lazy: no thread until first run()
    def run[T](self, coro: Coroutine[Any, Any, T]) -> T: ...
    def close(self) -> None: ...              # stops loop, joins thread

# src/pylzt/sync/client.py (new)
class SyncClient:
    """Synchronous facade over Client — identical constructor args, blocking methods.
    Not a Client subclass — wraps one internally, same composition pattern as the
    async namespaces."""
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._async_client = Client(*args, **kwargs)
        self._runner = SyncRunner()
        self.market = SyncMarketNamespace(self._async_client.market, self._runner)
        self.forum = SyncForumNamespace(self._async_client.forum, self._runner)
        self.antipublic = SyncAntipublicNamespace(self._async_client.antipublic, self._runner)
    def close(self) -> None: ...              # runs aclose() via runner, then runner.close()
    def __enter__(self) -> "SyncClient": return self
    def __exit__(self, *exc: object) -> None: self.close()
```

**Codegen change**: `generator.py` gains a sync-rendering mode that, for each already-
generated async facade method, emits a synchronous counterpart in a parallel file
(`facades/sync_market.py`, `sync_forum.py`, `sync_antipublic.py`) with the same
signature/docstring but a `def` (not `async def`) body calling
`self._runner.run(self._async.method_name(**kwargs))`. Runs once per site, right after
the existing async facade render, reusing the same field/type extraction — it does not
re-parse the OpenAPI spec, just re-renders the already-computed method signatures in
sync form.

**Non-goal**: no context-manager-free thread leak — `SyncClient` must be usable as a
context manager (`with SyncClient(...) as client:`) and `close()` must be safe to call
without one (idempotent, no error if called twice).

## README / positioning (added at user request)

Rewrite `README.md` as a presentation-quality landing doc — the current version is a
plain feature list. Position pylzt as **a framework**, not a thin SDK: token pool +
proxy pool + retry/circuit-breaker + batch coalescing + TTL cache + generic method-as-
class + facade codegen + sync/async dual API + media upload + multi-domain namespaces
is a genuinely framework-shaped feature set, not a wrapper. Include a "Quickstart in 30
seconds" block, a side-by-side async/sync example, a pagination example, an error-
handling example, a media-upload example, and a "why a framework, not a library"
paragraph naming the concrete architectural pieces (not marketing fluff — each claim
points at a real module). Scheduled as the LAST task (T14) since it should document the
final post-refactor API shape, not the pre-refactor one.

## Worktree

`../pylzt-api-namespaces` on branch `feat/api-namespaces`, based on `main`.

# entry-points-plugin-discovery — overview

**Tier:** module-lite · **Mode:** layered, solo, one pass

## Goal
Auto-load third-party `BaseMiddleware`/`BaseMetrics` implementations via
`importlib.metadata` entry points (`pylzt.plugins.middleware` /
`pylzt.plugins.metrics`) instead of manual registration — feeds the
existing `MiddlewareManager`/`BaseMetrics` seam, is an autoload *mechanism*,
not a second registry.

## Scope
- New file `src/pylzt/plugins.py` — `discover_middlewares()` (loads every
  `pylzt.plugins.middleware` entry point, zero-arg-constructs each),
  `discover_metrics()` (loads the single `pylzt.plugins.metrics` entry
  point if present).
- **Discovery point: `Client.__init__`, loaded once**, not `HttpxSession`
  self-discovery — confirmed `Client` is the composition root
  (`verified-by-code:src/pylzt/client.py`, `@final` class, `_raw_transport`
  currently builds `HttpxSession` with no middlewares threaded through at
  all — `verified-by-code:src/pylzt/client.py` exact body confirmed: no
  `middlewares=` kwarg passed today). Self-discovery inside `HttpxSession`
  was rejected: it would re-run `entry_points()` up to 3x per `Client`
  (market/forum/antipublic transports), constructing plugin instances
  redundantly, and `HttpxSession`'s own docstring scopes it to pure dispatch
  with no rate-limit/retry/discovery logic.
- **Metrics precedence**: `Client.metrics` is a single field
  (`BaseMetrics | None`), not a chain — explicit `metrics=` arg always wins.
  If not passed and discovery enabled: 0 found → `NullMetrics()` (unchanged
  default); 1 found → use it; **2+ found → raise `AmbiguousPlugin`** (fail
  loud, not first-found-wins — observability backend choice is worth an
  explicit failure on a packaging accident, caller disambiguates via
  `metrics=`). Middleware composes additively (that's `MiddlewareManager`'s
  whole point, existing dedup-by-`stable_id`) — all discovered middlewares
  register, no ambiguity to resolve there.
- `ClientConfig.enable_plugin_discovery: bool = True` — opt-out toggle. This
  is the **first** boolean field in `ClientConfig`
  (`verified-by-code:src/pylzt/config.py`, confirmed 12 existing fields,
  none boolean) — no prior convention to clash with.
- `pyproject.toml`: **no entry-point section added** — this repo is the
  plugin *host*, not a producer, confirmed no first-party plugin exists to
  register. The two-group convention is documented as a worked example for
  third-party consumer packages (in `plugins.py`'s module docstring).

## Non-goals
- No composite/fan-out metrics wrapper (`CompositeMetrics`) — explicitly
  rejected, would turn a discovery *mechanism* into a framework; the 2+
  ambiguity is a hard error instead.
- No entry-point group for anything beyond middleware/metrics (no
  `token_pool`/`proxy_source`/`retry` plugin groups) — those seams already
  take an explicit constructor arg with no manual-registration friction to
  solve; out of scope unless a real need surfaces.
- No change to `HttpxSession`'s existing `middlewares: Sequence[BaseMiddleware] = ()`
  constructor param — it's already exactly the injection seam needed, reused
  as-is.

## Files touched
- `src/pylzt/plugins.py` — **new**, `discover_middlewares()`,
  `discover_metrics()`, `MIDDLEWARE_GROUP`/`METRICS_GROUP` constants.
- `src/pylzt/errors.py` — `AmbiguousPlugin(LztError)` (verify `LztError`'s
  base constructor convention before matching it exactly — flagged
  `unverified` pending a quick read, not blocking the contract shape).
- `src/pylzt/config.py` — `enable_plugin_discovery: bool = True`.
- `src/pylzt/client.py` — `Client.__init__` resolves
  `self._plugin_middlewares`/`self._metrics` from discovery (gated by the
  toggle) before building any transport; `_raw_transport` passes
  `middlewares=self._plugin_middlewares` into `HttpxSession` (currently
  passes none). New imports:
  `from pylzt.plugins import discover_metrics, discover_middlewares`,
  confirm `BaseMiddleware` import status (verify not already
  `TYPE_CHECKING`-only before writing — flagged `unverified`).
- `tests/pylzt/test_plugins.py` — **new**, `discover_middlewares`/
  `discover_metrics` against fake `importlib.metadata.EntryPoint` objects
  (0/1/2+ registered cases).
- `tests/pylzt/test_client.py` — discovery wiring: toggle off → no
  discovery attempted; explicit `metrics=` always wins over a discovered one.

## Contracts/Types (frozen)

```python
# src/pylzt/plugins.py — new file
"""Third-party plugin discovery via importlib.metadata entry points.

Two entry-point groups feed the existing seams -- `pylzt.plugins.middleware`
(BaseMiddleware, composed additively into every transport) and
`pylzt.plugins.metrics` (BaseMetrics, exactly one sink). Discovery only
resolves + zero-arg-constructs; it never imports transports itself.

Worked example for a third-party consumer package's pyproject.toml:

    [project.entry-points."pylzt.plugins.middleware"]
    my_middleware = "my_pkg.middleware:MyMiddleware"

    [project.entry-points."pylzt.plugins.metrics"]
    my_metrics = "my_pkg.metrics:MyMetrics"
"""

MIDDLEWARE_GROUP = "pylzt.plugins.middleware"
METRICS_GROUP = "pylzt.plugins.metrics"

def discover_middlewares() -> tuple[BaseMiddleware, ...]:
    """Load every pylzt.plugins.middleware entry point as a zero-arg middleware."""

def discover_metrics() -> BaseMetrics | None:
    """Load the single pylzt.plugins.metrics entry point, or None if none
    registered. Raises AmbiguousPlugin if 2+ are registered."""

# src/pylzt/errors.py
class AmbiguousPlugin(LztError):
    def __init__(self, group: str, names: list[str]) -> None: ...
        # message: f"{len(names)} plugins registered for {group!r}: {names}"

# src/pylzt/config.py — ClientConfig, add field:
enable_plugin_discovery: bool = True

# src/pylzt/client.py — Client.__init__, after self.config resolved:
self._plugin_middlewares: tuple[BaseMiddleware, ...] = (
    discover_middlewares() if self.config.enable_plugin_discovery else ()
)
self._metrics = metrics or (
    (discover_metrics() if self.config.enable_plugin_discovery else None)
    or NullMetrics()
)

# Client._raw_transport — add middlewares kwarg, no signature change:
def _raw_transport(self, base_url: str) -> BaseTransport:
    return HttpxSession(
        base_url=base_url,
        timeout=self.config.request_timeout,
        middlewares=self._plugin_middlewares,
    )
```

## Worktree
`../aiolzt-entry-points-plugin-discovery` on branch `feat/entry-points-plugin-discovery`, based on `main`.

## Risks / edge cases
- **Explicit-transport bypass**: a caller passing `transport=`/
  `forum_transport=`/`antipublic_transport=` directly bypasses
  `_raw_transport` entirely, so plugin middlewares won't apply to that
  caller-owned transport. Mirrors existing behavior (`config.request_timeout`
  also doesn't reach an explicit transport) — no special-casing needed,
  documented as expected.
- **`@final` on `Client`**: only forbids subclassing, does not block editing
  `__init__`/`_raw_transport` directly — confirmed no obstacle.
- **Zero-arg construction assumption**: `discover_middlewares`/
  `discover_metrics` call `ep.load()()` — assumes every registered plugin
  class has a no-arg constructor. If a real third-party plugin needs config,
  it's out of scope for this plan (the plugin author's constructor should
  default every param); documented as a discovery-mechanism constraint, not
  solved with a config-passing protocol here (YAGNI until a real need).
- **`AmbiguousPlugin` base-class convention**: flagged `unverified` — confirm
  `LztError`'s exact constructor shape (args-carrying vs message-only) before
  implementation; correct at code time if the assumed shape is wrong (cheap,
  doesn't change the contract's field names).

## Success criteria (verifiable)
1. `discover_middlewares()` returns a middleware instance for each
   registered `pylzt.plugins.middleware` entry point (tested against fake
   entry points, no real third-party package needed).
2. `discover_metrics()` returns `None` on zero registrations, the loaded
   instance on exactly one, raises `AmbiguousPlugin` on two or more.
3. `Client(metrics=SomeMetrics())` always uses `SomeMetrics()` regardless of
   what's discoverable — explicit always wins.
4. `Client(config=ClientConfig(enable_plugin_discovery=False))` never calls
   `entry_points()` — toggle fully disables discovery, zero side effects.
5. `RELEASE-READY` pseudo-task passes.

## Decisions log
- **Discovery in `Client.__init__`, not `HttpxSession`** —
  `verified-by-code:src/pylzt/client.py` (composition-root convention,
  avoids 3x redundant `entry_points()` calls).
- **Fail loud (`AmbiguousPlugin`) over first-found-wins for metrics** —
  `unverified` (product/safety judgment call — observability backend choice
  is worth an explicit failure over silent nondeterminism).
- **No entry-point section added to this repo's own `pyproject.toml`** —
  `verified-by-code:pyproject.toml` (no first-party plugin exists; repo is
  host, not producer).
- **First boolean field in `ClientConfig`** —
  `verified-by-code:src/pylzt/config.py` (12 existing fields, all
  non-boolean; no convention conflict).

## Code-verification (W3.5, single Sonnet audit — module-lite)
Full Sonnet audit ran against real source. One 🟡 correction folded in:
`MiddlewareManager.middlewares` is a `@property`, not a callable method
(doesn't affect this plan's contracts directly, noted for implementer
awareness). Confirmed `MiddlewareManager.__call__` decorator-usage form
(`@session.request_middlewares`) exists alongside `register()` — irrelevant
to this plan's discovery mechanism, which uses `register()` directly inside
`HttpxSession.__init__`'s existing loop, unchanged. Zero 🔴 blockers. Two
🟡 open items flagged `unverified` above (LztError base shape, BaseMiddleware
import status in client.py) — cheap to confirm at implementation time,
don't change the frozen contract shape.

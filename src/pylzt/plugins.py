"""Third-party plugin discovery via `importlib.metadata` entry points.

Two entry-point groups feed the existing seams — `pylzt.plugins.middleware`
(`BaseMiddleware`, composed additively into every transport) and
`pylzt.plugins.metrics` (`BaseMetrics`, exactly one sink). Discovery only
resolves + zero-arg-constructs; it never imports transports itself.

Worked example for a third-party consumer package's `pyproject.toml`:

    [project.entry-points."pylzt.plugins.middleware"]
    my_middleware = "my_pkg.middleware:MyMiddleware"

    [project.entry-points."pylzt.plugins.metrics"]
    my_metrics = "my_pkg.metrics:MyMetrics"

This repo has no first-party plugin to register — it's the plugin host, not
a producer; the entry-point sections above live in a *consumer's* project.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from pylzt.errors import AmbiguousPlugin
from pylzt.lib.metrics import BaseMetrics
from pylzt.transport.middleware import BaseMiddleware

MIDDLEWARE_GROUP = "pylzt.plugins.middleware"
METRICS_GROUP = "pylzt.plugins.metrics"


def discover_middlewares() -> tuple[BaseMiddleware, ...]:
    """Load every `pylzt.plugins.middleware` entry point as a zero-arg middleware."""
    return tuple(ep.load()() for ep in entry_points(group=MIDDLEWARE_GROUP))


def discover_metrics() -> BaseMetrics | None:
    """Load the single `pylzt.plugins.metrics` entry point, or `None` if none
    registered. Raises `AmbiguousPlugin` if 2+ are registered — metrics is a
    single sink, not a chain; pass `metrics=` explicitly to disambiguate."""
    found = list(entry_points(group=METRICS_GROUP))
    if not found:
        return None
    if len(found) > 1:
        raise AmbiguousPlugin(group=METRICS_GROUP, names=[ep.name for ep in found])
    return found[0].load()()  # type: ignore[no-any-return]

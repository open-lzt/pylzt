# Logic — api-namespaces

## Flow: constructing a namespaced Client

1. `Client.__init__` builds `token_pool` exactly as today (market+forum tokens, shared).
2. **New**: if `antipublic_key` is given, builds a dedicated `RateLimitedTransport` for
   AntiPublic using a minimal single-credential pool (see Types — `_StaticBearerPool`, an
   internal `BaseTokenPool` implementation wrapping one fixed Bearer value, so
   `RateLimitedTransport`'s existing lease/sign/retry rail works unmodified for a
   single-credential target without inventing a parallel transport mechanism).
3. `Client.__init__` constructs the 3 namespaces last, each handed `self`:
   `self.market = MarketNamespace(self)`, `self.forum = ForumNamespace(self)`,
   `self.antipublic = AntipublicNamespace(self)`.
4. A caller does `await client.market.get_lot(item_id=...)` →
   `MarketNamespace.get_lot` (hand-written, moved from `Client`) → builds/executes
   `GetLot(item_id=...)` via `self.execute(...)` → `_Namespace.execute` → delegates to
   `self._client.execute(method)` → unchanged `Client.execute` (lease → transport →
   parse → `_bind`).
5. A caller does `await client.forum.forums_list()` → generated `GeneratedForumFacade`
   method body (**byte-for-byte unchanged from today**) → `self.execute(ForumsList())` →
   resolves to `_Namespace.execute` (MRO: `ForumNamespace(_Namespace, GeneratedForumFacade)`
   — `_Namespace` first so its `execute` wins) → same delegation as above.
6. `client.execute_batch(...)`, `client.reconfigure(...)`, `client.aclose()` stay
   top-level — unaffected by namespacing, since they're cross-cutting rail operations,
   not domain method calls.

## Why MRO order matters (`_Namespace` before `GeneratedXFacade` in bases)

`class MarketNamespace(_Namespace, GeneratedMarketFacade)` — Python resolves `execute`
by MRO left-to-right, so `_Namespace.execute` (the delegating override) wins over
whatever `GeneratedMarketFacade` would provide (it provides none today, but the explicit
order also future-proofs against a generated facade ever accidentally defining its own
`execute`).

## AntiPublic's rate-limit shape is genuinely different (see Risks)

AntiPublic's docs describe a **simultaneous-connection limit**, not a
requests-per-minute bucket like Market (120/min) or Forum (300/min). The existing
`RoundRobinTokenPool`'s bucket math (`general_per_min`, `search_per_min`, `forum_per_min`)
is a per-minute token-bucket model — it does not natively express "N concurrent in
flight". Task T3 must confirm via a live `/checkAccess` call whether AntiPublic's limit
is actually enforceable with the existing per-minute bucket (treating "concurrent
connections" as a proxy for "requests/min" is an approximation, not a verified
equivalence) or needs a semaphore-style concurrency limiter instead (`asyncio.Semaphore`
sized from the live `/checkAccess` response, bulkhead pattern) layered alongside the
existing rate-limited transport.

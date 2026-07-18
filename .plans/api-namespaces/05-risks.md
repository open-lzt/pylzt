# Risks — api-namespaces

## R1 — AntiPublic's rate-limit shape is unverified (🟡, blocks T2/T4 defaults)

AntiPublic's docs describe a **simultaneous-connection** limit ("The number of
simultaneous connections is limited... depends on subscription type"), explicitly
calling out "Limit of simultaneous connections is not a limit of requests per second."
This may not map cleanly onto the existing per-minute token-bucket model
(`RoundRobinTokenPool`'s `general_per_min`-style fields). **Before T2 ships**, make one
live `/checkAccess` call (needs a real AntiPublic key — ask the user for one, or mark
this task blocked-pending-credentials) and read the actual `subscription`/rate-limit
shape in the response to confirm whether a per-minute bucket is an adequate
approximation or a concurrency semaphore (`asyncio.Semaphore`) is the correct primitive.
`defer`-risk if no key is available before build starts — T2's bucket-based
`_StaticBearerPool` ships as the best-effort default, with this doc note attached to its
docstring so a future pass can swap the primitive without an API change (the
`BaseTokenPool.lease()` contract doesn't care which internal enforcement mechanism is used).

## R2 — `client.antipublic` exists even without `antipublic_key` — what happens on call?

Decided: `Client.__init__` always constructs `self.antipublic = AntipublicNamespace(self)`
regardless of whether `antipublic_key` was passed (consistent with `market`/`forum`
always existing). Calling any `client.antipublic.*` method without a key configured must
raise a **typed** error (not a bare `AttributeError`/`None`-related `TypeError`) —
mirrors `ModelNotBound`'s "fail loud, never a silent no-op" convention already
established for `BoundModel`. T6 must add a narrow check (in `_StaticBearerPool`'s
construction path, or a guard inside `AntipublicNamespace.execute`) that raises a
**new** typed error — `CredentialMissing(credential="antipublic_key")` in `errors.py`.
**CORRECTED (W3.5 finding)**: reusing `DependencyMissing` here is NOT a clean fit —
`verified-by-code:src/pylzt/errors.py` + its one real call site
(`transport/session.py:112`, `DependencyMissing(extra="httpx")`) shows its `ErrorCode`,
docstring, and only usage are scoped specifically to "optional pip package not
installed"; surfacing it for a missing credential would misleadingly suggest `pip
install antipublic_key`. `CredentialMissing` is a <10-line addition, carries the
credential name as an arg per the project's typed-exception convention (see 03-types.md).

## R3 — Breaking change is safe only because the library is unpublished (re-confirm before build)

This entire plan assumes zero external consumers of the current flat
`client.<method>()` surface. If between planning and build the user publishes a first
PyPI release, this plan's Non-goals section (no deprecation shim) becomes wrong and T6-T8
need a compatibility-alias pass added before merging. **Confirm at build time**, not just
at plan time.

## R4 — `MarketNamespace`/`ForumNamespace`/`AntipublicNamespace`: export or not?

**REVISED (W3.5 finding)**: `verified-by-code:src/pylzt/__init__.py:70-135` — the full
66-entry `__all__` currently exports **neither** `GeneratedMarketFacade` nor
`GeneratedForumFacade` (the very types being replaced), and none of `client.py`/
`facades/market.py`/`facades/forum.py` define their own `__all__` either. So exporting
the 3 new namespace classes would be a **reversal** of existing precedent, not a
continuation of it, as R4 originally assumed. T8 makes an explicit call (not a default):
keep them unexported (matching current practice — a consumer type-hints via
`pylzt.Client` and accesses `.market`/`.forum`/`.antipublic` structurally, never
imports the namespace class by name) unless the user says otherwise at Present time.

## Cross-plan risk

`media-upload` (`.plans/media-upload/`) touches `client.py`'s `execute()` /
`Client.__init__` too (media_storage param, T6 there). **These two plans conflict on the
same file** (`client.py`) if built in parallel — `swarm-build` must sequence them
(whichever lands first rebases the other), not run both worktrees' `client.py` changes
concurrently. Flagging here since both plans independently claim `client.py` edits.

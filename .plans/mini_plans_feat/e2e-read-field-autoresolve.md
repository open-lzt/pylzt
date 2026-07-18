## Goal
Extend `tests/pylzt/e2e/test_live_read.py`'s auto-discovery to also exercise the ~50
GET methods that DO have required fields (currently silently skipped, only the 74
zero-arg GET methods run) — resolve real field values live instead of guessing constants.

## Touch
- `tests/pylzt/e2e/test_live_read.py` only.

## Contracts/Types
`_FieldResolver = Callable[[Client], Awaitable[Any]]` — async resolver keyed by field name,
returns a real live value (or raises/returns None if unresolvable this run). Resolvers are
memoized per test session (module-level dict, populated lazily) so 20 methods needing
`thread_id` don't re-fetch the thread list 20 times.

## Approach
1. `_discover_get_methods()` — drop the `not any(f.is_required() ...)` filter; instead
   collect ALL GET methods and, per method, compute `required_fields = [f for f in
   model_fields if is_required]`.
2. New `GET_METHODS_WITH_ARGS` list (method_cls, required_fields tuple).
3. `_RESOLVERS: dict[str, _FieldResolver]` — one entry per field name actually seen across
   the 50 methods (item_id, category, currency, user_id, thread_id, forum_id, post_id,
   conversation_id, message_id, tag/tag_id, notification_id, page_id, link_id,
   profile_post_id, comment_id, search_id, type, limit, room_id). Verify each resolver's
   target facade method/response attribute against the LIVE API before trusting it (no
   guessing field names from memory — the project's hard rule).
4. `test_get_endpoint_with_resolved_args` — parametrized over `GET_METHODS_WITH_ARGS`;
   resolve each required field via `_RESOLVERS`, `pytest.skip` (not fail) if a field has no
   resolver or the resolver itself returns None (nothing live to feed it) — call the method,
   same `_EXPECTED_GAPS` xfail handling as the zero-arg test (a resolved id belonging to
   another token still 403/404s legitimately).

## Risk/edge
Resolvers that hit "managing" (seller-only) endpoints with a publicly-found item_id will
often legitimately 403/404 — already covered by `_EXPECTED_GAPS`, not a special case.
A resolver's own live call can itself fail (network/auth) — let that propagate as a real
test error for that resolver's dependents, don't silently skip a systemic outage.

## Test
Run `pytest -m e2e` with `LZT_E2E_TOKEN` set — confirm the new parametrized test collects
~50 additional cases and most pass/xfail cleanly (not error).

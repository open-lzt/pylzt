# Improvements — api-namespaces

## Tech debt to fix in this plan

| ID | Finding | Where | Cost | Decision |
|---|---|---|---|---|
| TD-1 | `Client` mixin-inheritance contradicts its own "composition root" docstring | `client.py:71` | M | must-include (this plan's whole point) |

## Future-proofing proposals

| ID | Proposal | Pays off when | Cost | Tag |
|---|---|---|---|---|
| FP-1 | Generalize `_Namespace.execute()` delegation base so a 4th future API target (if lzt ever ships one) only needs a new namespace class + codegen site entry, zero client.py changes | a 4th API target is added | S | must-include (near-zero extra cost given T7 already builds this base) |
| FP-2 | Rename `ClientConfig.base_url` → `market_base_url` for naming consistency with `forum_base_url`/`antipublic_base_url` | someone new reads config.py and asks "why is market special" | M | defer (own blast radius — every `ClientConfig(base_url=...)` call site, docs, README) |

## Deferred (logged for next plan)

- FP-2 (config field renaming) — separate future plan, not blocking this one.
- TD-2 from `00-audit.md` (same item as FP-2).

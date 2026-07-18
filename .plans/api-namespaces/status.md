# Status: api-namespaces

## Pipeline Progress
- [x] Stage 1: PLAN — architecture & decomposition
- [x] Stage 1.5: APPROVE — user approved plan
- [x] Stage 2: BUILD — main-agent sequential execution (T1-T14, all tasks done)
- [x] Stage 3: REVIEW — Opus sub-agent review of T1-T11 diff (2 passes, no critical
      bugs; 2 low-severity findings fixed — SyncRunner race, defensive _transport_for)
- [x] Stage 4: FIX — ruff/ruff format/mypy/pytest all green (128 passed, 1 skipped)
- [x] Stage 5: REPORT — merged into main, pushed

## Build Agents
Solo, main agent, no fan-out (per user instruction: "мейн-агентом"). Two Haiku
explore agents used only for pre-implementation context gathering (token_pool/
clock/errors patterns), not for writing code.

## Review Agents
1 Opus review agent (2 rounds — verified findings against live source, not
just the diff): confirmed CredentialMissing propagation, MarketNamespace
attribute rewiring, _StaticBearerPool lock ordering, gather_or_raise
semantics all correct. Fixed: SyncRunner run()/close() race (unified lock),
loop.close() after run_forever() (was leaking), defensive `case _` in
_transport_for.

## Fix Rounds
1. Media import bug surfaced by fixing GEN_MARKER staleness (async + sync
   facade renderers both omitted `Media` from their import scan — market/
   forum had never actually regenerated since media-upload landed, so this
   was latent until T11 forced a real regen).
2. Post-review: SyncRunner race + _transport_for defensive fallback.

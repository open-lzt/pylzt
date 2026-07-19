"""Client configuration — every knob frozen and explicit (no magic literals)."""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict


class ClientConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    # These are the real hosts AS7's Market/Forum clients pin internally (verified
    # live 2026-07-03) — LolzteamTransport doesn't pass base_url through to them, so
    # this mainly documents the truth; it matters if a caller swaps in a custom
    # transport that does respect it.
    # Rate limits are the official published ceilings (lzt-market.readme.io /
    # lolzteam.readme.io "Rate limit" sections, confirmed 2026-07-04): Market 120/min
    # general + 20/min Category Search; Forum 300/min.
    base_url: str = "https://prod-api.lzt.market"
    general_per_min: int = 120
    search_per_min: int = 20
    forum_base_url: str = "https://prod-api.lolz.live"
    forum_per_min: int = 300
    request_timeout: float = 30.0
    per_page: int = 50
    # Coalescing window width for BatchExecutor.submit(); the server's real per-request
    # cap is a separate, unconfigurable constant (`lib.batch.MAX_BATCH_JOBS = 10`,
    # verified live 2026-07-03) — a flush over that width is auto-chunked, not truncated.
    batch_size: int = 50
    batch_linger: float = 0.05
    category_params_ttl: float = 3600.0
    # AntiPublic (antipublic.one) — a separate leak-checking API, own Bearer license
    # key (see client.py `antipublic_key`, token_pool/_static.py). `antipublic_per_min`
    # is a PLACEHOLDER: the docs describe the limit as "simultaneous connections", not
    # requests/min like Market/Forum, so this may not even be the right shape — revisit
    # once a live `/checkAccess` call confirms the real limit contract (see 05-risks.md).
    antipublic_base_url: str = "https://antipublic.one/api/v2"
    antipublic_per_min: int = 60
    # Server-reported system_info.rate_limit reconciliation (see
    # token_pool/rate_limit.py). On by default because the reconcile is
    # clamp-only — it only tightens local budget, never grants extra, so
    # it's a safety behavior, not a risky one. Escape hatch if it misbehaves.
    enable_server_rate_sync: bool = True
    # Auto-load third-party BaseMiddleware/BaseMetrics via importlib.metadata
    # entry points (pylzt.plugins.*, see plugins.py). Escape hatch for a
    # packaging accident (e.g. two metrics plugins installed) or to keep
    # startup deterministic without scanning installed distributions.
    enable_plugin_discovery: bool = True
    # AIMD concurrency auto-tuning off the server rate-limit signal (see
    # token_pool/governor.py). Off by default, unlike enable_server_rate_sync:
    # clamp-only reconcile only tightens (a pure safety behavior); AIMD
    # actively changes live throughput and can misfire (too aggressive or
    # too lenient), so it's a behavior change that ships opt-in.
    enable_adaptive_concurrency: bool = False

    @classmethod
    def for_testnet(cls, **overrides: object) -> ClientConfig:
        """Point market + forum at a local lzt-testnet mock in one call.

        Reads ``LZT_TESTNET_HOST`` / ``LZT_TESTNET_PORT`` (default ``127.0.0.1:8765``) — the same
        env the mock server itself uses — so ``config=ClientConfig.for_testnet()`` replaces the
        hand-written ``base_url=`` / ``forum_base_url=`` boilerplate.
        """
        host = os.environ.get("LZT_TESTNET_HOST", "127.0.0.1")
        port = os.environ.get("LZT_TESTNET_PORT", "8765")
        base = f"http://{host}:{port}"
        # overrides win — dict merge, not duplicate-kwarg (which would TypeError on base_url=...)
        return cls(**{"base_url": base, "forum_base_url": base, **overrides})

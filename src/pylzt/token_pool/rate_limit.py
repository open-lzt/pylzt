"""Server ground-truth for a token's rate budget — `system_info.rate_limit`.

Every lzt.market response body carries `system_info.rate_limit`, but codegen
strips `system_info` from typed models (`dev/codegen/generator.py`) and
`LolzObject`'s `extra="ignore"` would silently drop it even if it reached
Pydantic. So this is parsed from the raw, undropped `Response.body` at the
transport layer instead — see `BaseTransport.send`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RateLimitSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    limit: int
    remaining: int
    reset: int
    bucket: str | None = None

    @classmethod
    def from_body(cls, body: dict[str, object]) -> RateLimitSnapshot | None:
        """`None` on any absent/malformed shape — never raises."""
        # Response.body's dict[str, object] type hint is a static contract only —
        # dataclasses don't validate it at runtime, and `body` crosses a trust
        # boundary (raw HTTP response JSON). Statically unreachable, not actually.
        if not isinstance(body, dict):
            return None  # type: ignore[unreachable]
        info = body.get("system_info")
        if not isinstance(info, dict):
            return None
        rate_limit = info.get("rate_limit")
        if not isinstance(rate_limit, dict):
            return None
        try:
            bucket = rate_limit.get("bucket")
            return cls(
                limit=int(rate_limit["limit"]),
                remaining=int(rate_limit["remaining"]),
                reset=int(rate_limit["reset"]),
                bucket=bucket if isinstance(bucket, str) else None,
            )
        except (KeyError, TypeError, ValueError):
            return None

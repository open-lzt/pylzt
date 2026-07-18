"""Typed error hierarchy for every upstream signal.

Each wire-facing `LztError` subclass self-registers via `__init_subclass__` (opt-in
with `__wire__ = True`) and owns a `check(status, headers, body)` classmethod that
decides whether it matches a raw response. `LztError.match(...)` walks the registry
in `__priority__` order (lower first) and returns the first hit, or `None` on
success — the one mechanism a transport calls to narrow a response to a typed
error. Registration order is irrelevant; only `__priority__` controls match order,
so reordering class definitions can never silently change matching.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from pylzt.types import ItemId, TokenId

if TYPE_CHECKING:
    from collections.abc import Mapping

_RETRY_REQUEST = "retry_request"
_STEAM_CAPTCHA = "steam_captcha"
_CAPTCHA = "captcha"


class ErrorCode(StrEnum):
    RATE_LIMITED = "rate_limited"
    RETRY_REQUEST = "retry_request"
    CAPTCHA = "captcha"
    STEAM_CAPTCHA = "steam_captcha"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    BAD_REQUEST = "bad_request"
    UPSTREAM_ERROR = "upstream_error"
    DEP_MISSING = "dep_missing"
    METHOD_DECLARATION = "method_declaration"
    MODEL_NOT_BOUND = "model_not_bound"
    BATCH_LIMIT = "batch_limit"
    CREDENTIAL_MISSING = "credential_missing"
    BATCH_JOB_FAILED = "batch_job_failed"
    MIXED_BATCH_API_TARGETS = "mixed_batch_api_targets"
    AMBIGUOUS_PLUGIN = "ambiguous_plugin"
    MEDIA_NOT_BATCHABLE = "media_not_batchable"


def _messages(body: Mapping[str, Any]) -> str:
    """Lowercased text of every error-ish field in a XenForo-style error envelope."""
    parts: list[str] = []
    errors = body.get("errors")
    if isinstance(errors, list):
        parts.extend(str(e) for e in errors)
    elif isinstance(errors, str):
        parts.append(errors)
    codes = body.get("error_codes")
    if isinstance(codes, list):
        parts.extend(str(c) for c in codes)
    for key in ("message", "error"):
        value = body.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


class LztError(Exception):
    """Root of the SDK error tree. Subclasses carry typed args, never text.

    Wire-facing subclasses opt into response-matching by setting `__wire__ = True`
    and overriding `check()`; declaration-time guards (`MethodDeclarationError`,
    `ModelNotBound`, `DependencyMissing`, `BatchLimitExceeded`) stay `__wire__ = False`
    and are never returned by `match()`.
    """

    code: ErrorCode
    __wire__: ClassVar[bool] = False
    __priority__: ClassVar[int] = 1000
    _registry: ClassVar[list[type[LztError]]] = []

    def __init__(self, code: ErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("__wire__"):
            LztError._registry.append(cls)
            LztError._registry.sort(key=lambda c: c.__priority__)

    @classmethod
    def check(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        """Return an instance if THIS class matches the raw response, else None."""
        return None

    @classmethod
    def match(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        """Walk the priority-ordered registry, return the first `check()` hit."""
        for err_cls in LztError._registry:
            hit = err_cls.check(status, headers, body)
            if hit is not None:
                return hit
        return None


class RateLimited(LztError):
    __wire__ = True
    __priority__ = 10

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(ErrorCode.RATE_LIMITED)

    @classmethod
    def check(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        if status != 429:
            return None
        raw = headers.get("retry-after")
        try:
            retry_after = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            retry_after = None
        return cls(retry_after)


class RetryableUpstream(LztError):
    __wire__ = True
    __priority__ = 20

    def __init__(self, hint: str) -> None:
        self.hint = hint
        super().__init__(ErrorCode.RETRY_REQUEST)

    @classmethod
    def check(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        if _RETRY_REQUEST in _messages(body):
            return cls(_RETRY_REQUEST)
        return None


class ProxyChallenge(LztError):
    """Upstream demanded a fresh exit IP (`steam_captcha`) — rotate proxy, retry."""

    __wire__ = True
    __priority__ = 30

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(ErrorCode.STEAM_CAPTCHA)

    @classmethod
    def check(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        if _STEAM_CAPTCHA in _messages(body):
            return cls(_STEAM_CAPTCHA)
        return None


class CaptchaRequired(LztError):
    __wire__ = True
    __priority__ = 40

    def __init__(self) -> None:
        super().__init__(ErrorCode.CAPTCHA)

    @classmethod
    def check(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        if _CAPTCHA in _messages(body):
            return cls()
        return None


class AuthFailed(LztError):
    __wire__ = True
    __priority__ = 50

    def __init__(self, token_id: TokenId) -> None:
        self.token_id = token_id
        super().__init__(ErrorCode.UNAUTHORIZED)

    @classmethod
    def check(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        return cls(TokenId("")) if status == 401 else None


class Forbidden(LztError):
    __wire__ = True
    __priority__ = 60

    def __init__(self, scope: str | None = None) -> None:
        self.scope = scope
        super().__init__(ErrorCode.FORBIDDEN)

    @classmethod
    def check(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        return cls(None) if status == 403 else None


class NotFound(LztError):
    __wire__ = True
    __priority__ = 70

    def __init__(self, item_id: ItemId | None = None) -> None:
        self.item_id = item_id
        super().__init__(ErrorCode.NOT_FOUND)

    @classmethod
    def check(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        return cls(None) if status == 404 else None


class BadRequest(LztError):
    __wire__ = True
    __priority__ = 80

    def __init__(self, field: str | None = None) -> None:
        self.field = field
        super().__init__(ErrorCode.BAD_REQUEST)

    @classmethod
    def check(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        return cls(None) if status == 400 else None


class TransportError(LztError):
    __wire__ = True
    __priority__ = 90

    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(ErrorCode.UPSTREAM_ERROR)

    @classmethod
    def check(
        cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> LztError | None:
        return cls(status) if status >= 500 else None


class DependencyMissing(LztError):
    """A required optional dependency (e.g. the AS7 backend) is not installed."""

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(ErrorCode.DEP_MISSING)


class CredentialMissing(LztError):
    """A namespace's call needs a credential the `Client` was never given (e.g.
    `client.antipublic.*` without `antipublic_key=`) — declaration-time guard, not a
    wire signal (`__wire__` stays False)."""

    def __init__(self, credential: str) -> None:
        self.credential = credential
        super().__init__(ErrorCode.CREDENTIAL_MISSING)


class MethodDeclarationError(LztError):
    """A `BaseMethod` subclass is mis-declared (import-time guard, never a wire signal)."""

    def __init__(self, method: str, reason: str) -> None:
        self.method = method
        self.reason = reason
        super().__init__(ErrorCode.METHOD_DECLARATION)


class ModelNotBound(LztError):
    """A bound-model operation (e.g. `lot.refresh()`) ran on a model with no client attached."""

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(ErrorCode.MODEL_NOT_BOUND)


class BatchLimitExceeded(LztError):
    """A single /batch request carried more jobs than the server-enforced cap."""

    def __init__(self, count: int, limit: int) -> None:
        self.count = count
        self.limit = limit
        super().__init__(ErrorCode.BATCH_LIMIT)


class BatchJobFailed(LztError):
    """One job in a `Client.execute_batch` call came back `_job_result: error` (or was
    absent from the response entirely) — its method never reached `parse_response`."""

    def __init__(self, job_id: str, method: str, upstream_error: str | None) -> None:
        self.job_id = job_id
        self.method = method
        self.upstream_error = upstream_error
        super().__init__(ErrorCode.BATCH_JOB_FAILED)


class MixedBatchApiTargets(LztError):
    """`Client.execute_batch` was given methods targeting both market and forum —
    `/batch` is host-specific, so one call can only cover one `ApiTarget`."""

    def __init__(self, targets: frozenset[str]) -> None:
        self.targets = targets
        super().__init__(ErrorCode.MIXED_BATCH_API_TARGETS)


class MediaNotBatchable(LztError):
    """A method carrying `Media` field(s) was routed through `/batch` (`execute_batch`,
    `job()`, or an active `batching()` scope) — the flat batch job format has no multipart
    slot, so the file would silently never reach the server. Fail loud instead of quietly
    dropping the upload: call this method through plain `execute()` outside any batch path."""

    def __init__(self, method: str, fields: tuple[str, ...]) -> None:
        self.method = method
        self.fields = fields
        super().__init__(ErrorCode.MEDIA_NOT_BATCHABLE)


class AmbiguousPlugin(LztError):
    """2+ third-party implementations registered under one `pylzt.plugins.*`
    entry-point group that only takes a single instance (e.g. metrics) — fail
    loud instead of picking one, the caller disambiguates via an explicit arg."""

    def __init__(self, group: str, names: list[str]) -> None:
        self.group = group
        self.names = names
        super().__init__(ErrorCode.AMBIGUOUS_PLUGIN)

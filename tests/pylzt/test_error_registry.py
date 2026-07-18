"""`LztError` self-registering check() registry — priority ordering, extensibility."""

from __future__ import annotations

from pylzt.errors import (
    AuthFailed,
    BadRequest,
    CaptchaRequired,
    Forbidden,
    LztError,
    NotFound,
    ProxyChallenge,
    RateLimited,
    RetryableUpstream,
    TransportError,
)


def test_status_maps_to_typed_error() -> None:
    assert isinstance(LztError.match(401, {}, {}), AuthFailed)
    assert isinstance(LztError.match(403, {}, {}), Forbidden)
    assert isinstance(LztError.match(404, {}, {}), NotFound)
    assert isinstance(LztError.match(400, {}, {}), BadRequest)
    assert isinstance(LztError.match(503, {}, {}), TransportError)
    assert LztError.match(200, {}, {}) is None


def test_rate_limited_reads_retry_after_header() -> None:
    err = LztError.match(429, {"retry-after": "12.5"}, {})
    assert isinstance(err, RateLimited)
    assert err.retry_after == 12.5


def test_rate_limited_without_header_has_no_retry_after() -> None:
    err = LztError.match(429, {}, {})
    assert isinstance(err, RateLimited)
    assert err.retry_after is None


def test_body_text_checks_win_over_status_bucket() -> None:
    # 400 + a captcha marker in the body -> CaptchaRequired, not BadRequest.
    err = LztError.match(400, {}, {"errors": ["captcha required"]})
    assert isinstance(err, CaptchaRequired)


def test_body_text_checks_run_regardless_of_2xx_status() -> None:
    err = LztError.match(200, {}, {"errors": ["retry_request needed"]})
    assert isinstance(err, RetryableUpstream)
    assert err.hint == "retry_request"

    err2 = LztError.match(200, {}, {"error": "steam_captcha triggered"})
    assert isinstance(err2, ProxyChallenge)


def test_steam_captcha_not_misread_as_plain_captcha() -> None:
    # "captcha" is a substring of "steam_captcha" — ProxyChallenge (priority 30) must win
    # over CaptchaRequired (priority 40), not the other way around.
    err = LztError.match(200, {}, {"message": "steam_captcha required"})
    assert isinstance(err, ProxyChallenge)


def test_non_wire_errors_never_registered() -> None:
    from pylzt.errors import (
        BatchLimitExceeded,
        DependencyMissing,
        MethodDeclarationError,
        ModelNotBound,
    )

    for cls in (BatchLimitExceeded, DependencyMissing, MethodDeclarationError, ModelNotBound):
        assert cls not in LztError._registry


def test_custom_subclass_self_registers() -> None:
    from collections.abc import Mapping
    from typing import Any

    from pylzt.errors import ErrorCode

    class _CustomRejected(LztError):
        __wire__ = True
        __priority__ = 5  # ahead of everything built-in

        def __init__(self) -> None:
            super().__init__(ErrorCode.BAD_REQUEST)

        @classmethod
        def check(
            cls, status: int, headers: Mapping[str, str], body: Mapping[str, Any]
        ) -> LztError | None:
            return cls() if body.get("custom_marker") else None

    assert _CustomRejected in LztError._registry

    err = LztError.match(200, {}, {"custom_marker": True})
    assert isinstance(err, _CustomRejected)

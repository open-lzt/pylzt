"""`LolzObject`'s two concessions to what the live API actually sends.

Both exist because the spec is a CLAIM about the API and repeatedly a false one, and both were
written after a live failure rather than from reading docs:

  * a field the spec calls required simply is not sent (`purchasing_check` omitted eleven of them,
    which made the price read before every purchase unparseable, which degraded every lot to
    "unavailable", which is why no autobuy could complete);
  * an object-typed field arrives as `[]`, because the backend is PHP and `json_encode` renders an
    empty associative array as a list (`GET /me` sends `restore_data`, `telegram_client` and
    `rendered.backgrounds` that way).

The asymmetry that justifies both: a wrongly-strict field makes the ENTIRE response unreadable, so
the caller loses the fifty fields that did arrive; a wrongly-lenient one costs an `is None` check.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pylzt.models.base import LolzObject


class _Nested(LolzObject):
    inner: str


class _Sample(LolzObject):
    required_scalar: int
    required_object: _Nested
    genuine_list: list[str]


def test_an_absent_field_is_none_rather_than_a_parse_failure() -> None:
    parsed = _Sample.model_validate({"genuine_list": ["a"]})

    assert parsed.required_scalar is None
    assert parsed.required_object is None
    assert parsed.genuine_list == ["a"]


def test_an_empty_list_in_an_object_field_reads_as_empty() -> None:
    """PHP has one array type, so `[]` IS the empty map — for every object field, not one call."""
    parsed = _Sample.model_validate(
        {"required_scalar": 1, "required_object": [], "genuine_list": []}
    )

    assert parsed.required_object is None
    # The rewrite must not reach a field that genuinely holds a list, or an empty collection would
    # silently become None and the caller would iterate over nothing-that-is-not-empty.
    assert parsed.genuine_list == []


def test_a_non_empty_list_in_an_object_field_still_raises() -> None:
    """The line this leniency does not cross.

    An empty list is a PHP serialisation artefact; a POPULATED one where an object belongs is a
    genuine contract change, and silencing that would hide the very thing worth being told about.
    """
    with pytest.raises(ValidationError):
        _Sample.model_validate({"required_object": [{"inner": "x"}]})


def test_a_present_value_is_untouched() -> None:
    parsed = _Sample.model_validate(
        {"required_scalar": 7, "required_object": {"inner": "x"}, "genuine_list": ["a", "b"]}
    )

    assert parsed.required_scalar == 7
    assert parsed.required_object is not None
    assert parsed.required_object.inner == "x"
    assert parsed.genuine_list == ["a", "b"]

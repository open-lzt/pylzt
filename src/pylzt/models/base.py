"""`LolzObject` — the base for every generated response model.

Owns the raw→model conversion so individual models never redeclare `from_raw`: a Pydantic
model with `populate_by_name=True` (a field can be set by its Python name or its wire alias)
and `extra="ignore"` (an upstream field addition never breaks parsing). The method layer's
`__returning__` calls `from_raw` for a single object body and `from_raw_many` for an array.

Also owns `BoundModel`, the client-binding mixin (aiogram-style): a response model returned
through `Client.execute` is bound to its client (`as_`), so it exposes convenience operations
on itself — `lot.refresh()` re-fetches through the same rail — without the caller threading
the client around. Binding is invisible to value semantics: `_client` is set via
`object.__setattr__`, never a declared field, so it stays out of equality/hash/repr and out
of Pydantic's own validation. A model used standalone (built or parsed without a client)
raises `ModelNotBound` if a bound op is called — fail loud, never a silent no-op. `LolzObject`
mixes `BoundModel` in directly so every generated model is bindable; a hand-written model that
needs its own `model_validate`-incompatible parsing (e.g. `Lot`, whose `from_raw` does real
transformation — nested seller extraction, timestamp parsing, `content_hash` computation, not
just `cls.model_validate(raw)`) inherits `BaseModel, BoundModel` directly instead of
`LolzObject`, to avoid colliding with `LolzObject.from_raw_many`'s incompatible signature.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, Optional, Self

from pydantic import BaseModel, ConfigDict

from pylzt.errors import ModelNotBound

if TYPE_CHECKING:
    from pylzt.client import Client


class BoundModel:
    def as_(self, client: Client) -> Self:
        """Attach the client that produced this model and return self (idempotent)."""
        object.__setattr__(self, "_client", client)
        return self

    @property
    def client(self) -> Client:
        """The bound client, or `ModelNotBound` if this model was never executed."""
        client: Client | None = getattr(self, "_client", None)
        if client is None:
            raise ModelNotBound(type(self).__name__)
        return client


class LolzObject(BaseModel, BoundModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """An absent field is `None`, never a ValidationError.

        The mirror of `extra="ignore"`. That one says an upstream field ADDITION must not break
        parsing; this one says the same about a field the response simply does not carry. The
        spec's `required` list is a claim about the API, and repeatedly a false one — measured
        against prod, `purchasing_check` (the call that reads a price ceiling before money moves)
        omits eleven fields the spec calls required, so the whole response was unparseable and
        every autobuy degraded to "lot unavailable".

        The costs are not symmetric. A wrongly-required field makes the ENTIRE response
        unreadable — the caller gets an exception instead of the fifty fields that did arrive. A
        wrongly-optional one costs an `is None` check.

        **The price, stated plainly: static types now over-promise.** A field declared `int` here
        can be `None` at runtime, and mypy will not warn about it. That is the deliberate trade
        for keeping `| None` out of ~400 generated models; the alternative widens every field's
        declared type and pushes the same check onto every caller of every field, including the
        vast majority that are always present.

        Applied to subclasses only — `LolzObject` itself declares no fields — and re-runs the
        schema build, so validation, not just construction, sees the defaults.
        """
        super().__pydantic_init_subclass__(**kwargs)
        loosened = False
        for field in cls.model_fields.values():
            if not field.is_required():
                continue
            # `Optional[...]`, not `... | None`: the annotation may still be an unresolved string
            # under `from __future__ import annotations`, and the `|` operator has no meaning on
            # one. `Optional` accepts both and normalises.
            field.annotation = Optional[field.annotation]  # type: ignore[assignment]  # noqa: UP045
            field.default = None
            loosened = True
        if loosened:
            cls.model_rebuild(force=True)

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> Self:
        """Parse one wire object into this model."""
        return cls.model_validate(raw)

    @classmethod
    def from_raw_many(cls, raw: Iterable[Mapping[str, Any]]) -> list[Self]:
        """Parse an array of wire objects into a list of this model."""
        return [cls.model_validate(x) for x in raw]


class BaseResponse(LolzObject):
    """Base for wire responses that carry the API's own `status` sentinel (`"ok"` on
    success). Codegen rebases any generated model with a leading `status: str` field onto
    this class and drops the field, so callers use `resp.is_ok()` instead of every model
    re-deriving the same `status == "ok"` comparison (see `_rebase_status_responses` in
    dev/codegen/generator.py)."""

    status: str

    def is_ok(self) -> bool:
        return self.status == "ok"

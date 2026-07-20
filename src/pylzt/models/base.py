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
        """Every response field becomes optional. Deliberate, and only on the response side.

        The OpenAPI spec marks almost everything required; the live API disagrees constantly —
        a field is absent on one item and null on the next, and which ones varies by category, by
        endpoint and by how the row was created. Each mismatch used to cost a hand-patch, and the
        failure mode is the worst kind: a `purchasing_fast_buy` that ALREADY MOVED MONEY raised a
        ValidationError on ten cosmetic fields, so the caller saw a failure for a purchase that
        succeeded.

        We do not control that server, so the model must absorb its variance instead of asserting
        it. This is Postel's law applied where it belongs — inbound only. `BaseMethod` (requests)
        stays strict, because there a missing field IS the caller's bug and catching it before the
        wire is the whole point of a typed SDK.

        Widening the annotation rather than only defaulting matters: it accepts both shapes the API
        actually produces — the field missing, and the field present as null.
        """
        super().__pydantic_init_subclass__(**kwargs)
        widened = False
        for field in cls.model_fields.values():
            annotation = field.annotation
            if annotation is None or not field.is_required():
                continue
            # `Optional[x]`, not `x | None`: identical at runtime, but the field's declared type is
            # `type[Any] | None`, and `|` on a possibly-None left operand does not type-check.
            field.annotation = Optional[annotation]  # type: ignore[assignment]  # noqa: UP045
            field.default = None
            widened = True
        if widened:
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

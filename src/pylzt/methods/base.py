"""Method-as-class — aiogram-style declarative endpoints, backed by a frozen Pydantic model.

A `BaseMethod[T]` is a **frozen Pydantic model**: a subclass declares its request fields as
model fields (no hand-written `__init__`) and fixes the wire intent with class-vars, exactly
like aiogram's `TelegramMethod`. Field validation runs on construction, catching a malformed
request before it ever reaches the transport.

Declarative class-vars (read by the default `build_request` / `parse_response`):

* ``__http_method__`` — `HttpMethod.GET | POST | PUT | DELETE`.
* ``__url__``         — path template; `{name}` placeholders are filled from the same-named
  request fields. Path params are derived from the URL itself — there is no separate list.
* ``__query_fields__`` / ``__body_fields__`` — optional explicit routing; default is by verb
  (GET → query string, POST → JSON body).
* ``__rate_class__``  — the rate-limit class the request leases under.
* ``__returning__``   — the response **model** whose `from_raw` the default `parse_response`
  applies, or the `passthrough` sentinel when the body is already a built-in (list / dict /
  int / str / ...). **Override `parse_response`** only when the wire shape needs real
  narrowing (a nested key, batch ordering, slug filtering).

`__init_subclass__` enforces the contract at import: a method must supply `__url__` (or
override `build_request`) and `__returning__` (or override `parse_response`), and may not use
`__path__` (Python reserves it). A flat read is then just fields + metadata:

    class GetLot(BaseMethod[Lot]):
        __http_method__ = HttpMethod.GET
        __url__ = "/{item_id}"
        item_id: ItemId

        # Overrides because the lot is nested under an "item" key. A method whose body IS
        # the DTO just sets `__returning__ = SomeModel` (or `passthrough` for a built-in)
        # and inherits the parent parse_response — no override needed.
        def parse_response(self, response: Response) -> Lot:
            return Lot.from_raw(response.body.get("item", response.body))

    lot = await client.execute(GetLot(item_id))
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict

from pylzt.errors import MethodDeclarationError
from pylzt.media import Media
from pylzt.models.base import LolzObject
from pylzt.transport.base import Request, RequestOptions
from pylzt.types import ApiTarget, HttpMethod, RateClass

if TYPE_CHECKING:
    from pylzt.transport.base import BaseTransport, Response

_URL_PLACEHOLDERS = re.compile(r"\{(\w+)\}")


class Passthrough:
    """Sentinel `__returning__` for a method whose response body is already a built-in
    (list / dict / int / str / ...) — the JSON decoder produced the right Python type, so
    parse_response returns it unchanged. Contrast a response model, whose `from_raw` runs.

    A sentinel (not a callable) on purpose: mypy treats a callable class-var assigned a
    function as a method override and rejects it under strict; a class/instance value does not.
    """

    __slots__ = ()


passthrough = Passthrough()


class BaseMethod[T](BaseModel):
    """Request method-as-class. A frozen Pydantic model: request params are model fields,
    the endpoint's shape is carried in `__*__` ClassVars. Subclasses that only share fields
    (no endpoint of their own — see `methods/_models/`) set `__abstract__ = True` to opt out
    of the endpoint-declaration checks."""

    model_config = ConfigDict(frozen=True)

    __abstract__: ClassVar[bool] = False
    __http_method__: ClassVar[HttpMethod] = HttpMethod.GET
    __url__: ClassVar[str] = ""
    __rate_class__: ClassVar[RateClass] = RateClass.GENERAL
    __api__: ClassVar[ApiTarget] = ApiTarget.MARKET
    __query_fields__: ClassVar[frozenset[str] | None] = None
    __body_fields__: ClassVar[frozenset[str] | None] = None
    __returning__: ClassVar[type[LolzObject] | Passthrough | None] = None
    __unwrap__: ClassVar[str | None] = None  # dig this single key out of the body before parsing

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        # Pydantic's hook (fires after the model is built) — not __init_subclass__, which also
        # runs for the intermediate `BaseMethod[X]` submodel Pydantic mints for every
        # `class Foo(BaseMethod[Resp])` and would wrongly fail the "needs __url__" check.
        super().__pydantic_init_subclass__(**kwargs)
        if cls.__dict__.get("__abstract__"):
            return  # a shared-field base, not a callable endpoint
        if cls.__pydantic_generic_metadata__["origin"] is not None:
            return  # a parametrized generic submodel (BaseMethod[X]), not an endpoint
        if "__path__" in cls.__dict__:
            raise MethodDeclarationError(cls.__name__, "use __url__, not __path__")
        if not cls.__url__ and "build_request" not in cls.__dict__:
            raise MethodDeclarationError(cls.__name__, "set __url__ or override build_request")
        if cls.__returning__ is None and "parse_response" not in cls.__dict__:
            raise MethodDeclarationError(
                cls.__name__, "set __returning__ or override parse_response"
            )

    def build_request(self) -> Request:
        """Fill `{placeholder}`s in `__url__` from same-named fields; route the rest to query/body.

        Path params are derived straight from the URL template — no separate declaration —
        so a `{order}` in the path is filled by the `order` field and every other field
        becomes a query/body param."""
        values = {
            name: getattr(self, name)
            for name in type(self).model_fields
            if getattr(self, name) is not None
        }
        names = _URL_PLACEHOLDERS.findall(self.__url__)
        path = (
            self.__url__.format(**{k: values[k] for k in names if k in values})
            if names
            else self.__url__
        )
        rest = {k: v for k, v in values.items() if k not in names}
        media = {k: v for k, v in rest.items() if isinstance(v, Media)}
        if media:
            # httpx forbids json= together with files= — the non-file fields ride as
            # multipart form data instead (see transport/session.py `_do_wire_send`).
            non_media = {k: v for k, v in rest.items() if k not in media}
            return Request(
                method=self.__http_method__,
                path=path,
                rate_class=self.__rate_class__,
                json_body=non_media or None,
                files=media,
            )
        query, body = self._route(rest)
        return Request(
            method=self.__http_method__,
            path=path,
            rate_class=self.__rate_class__,
            query=query,
            json_body=body,
        )

    def _route(self, rest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if self.__query_fields__ is not None:
            return {k: rest[k] for k in self.__query_fields__ if k in rest}, None
        if self.__body_fields__ is not None:
            return {}, {k: rest[k] for k in self.__body_fields__ if k in rest}
        if self.__http_method__ is HttpMethod.GET:
            return rest, None
        return {}, rest

    def parse_response(self, response: Response) -> T:
        """Default: parse the body via `__returning__` — a model's `from_raw`, or, for the
        `passthrough` sentinel, the body as-is (or `response.text` for the handful of
        endpoints whose 200 is a bare string, not JSON — see `Response.text`).
        Override only for custom wire shapes."""
        returning = type(self).__returning__
        if returning is None:  # unreachable for a valid subclass (__init_subclass__ guards it)
            raise MethodDeclarationError(type(self).__name__, "no __returning__/parse_response")
        body: Any = response.body
        if self.__unwrap__ is not None and isinstance(body, Mapping):
            body = body.get(self.__unwrap__)  # single-field response root → its payload
        if isinstance(returning, Passthrough):
            return cast("T", response.text if response.text is not None else body)
        if isinstance(body, list):
            return cast("T", returning.from_raw_many(body))
        return cast("T", returning.from_raw(body))

    async def __call__(self, transport: BaseTransport, options: RequestOptions | None = None) -> T:
        """Run this method over a transport, optionally overriding transport details for the call.

        The options are stamped onto the built Request rather than passed into `build_request`,
        because `build_request` is part of the public override contract — a subclass that narrows
        an odd wire shape defines `build_request(self)`, and widening the signature would break
        every such override in the wild. Same reason the transport stamps the leased bearer this
        way instead of asking each method to carry one.
        """
        request = self.build_request()
        if options is not None:
            request = request.model_copy(update={"options": options})
        return self.parse_response(await transport.send(request))

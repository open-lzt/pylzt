# Media upload — architecture verification (07)

Cross-checked every plan claim in `00-overview.md` / `04-tasks.yaml` against the live source
in `src/pylzt/` (read via explore pass) and against real pydantic v2 / httpx behavior
(verified via sandbox scripts, not memory).

## 1. `transport/base.py` — `Request` shape

**CONFIRMED.** `src/pylzt/transport/base.py:28-40`:

```python
@dataclass(frozen=True, slots=True)
class Request:
    method: str
    path: str
    rate_class: RateClass
    query: dict[str, Any] = field(default_factory=dict)
    json_body: dict[str, Any] | list[Any] | None = None
    bearer: str | None = None
    proxy: ProxySpec | None = None
```

Frozen, `slots=True`, exact field list matches the plan's assumption. Adding
`files: Mapping[str, Media] | None = None` as an eighth field is mechanically safe:
`@dataclass(slots=True)` regenerates `__slots__` from the full annotated field list at class
body evaluation time (not additively), so a new field is just one more slot — no conflict.
`frozen=True` only blocks post-init mutation, not adding new declared fields. No circular
import risk: `media.py` (plan's location) imports nothing from `transport/`, and
`transport/base.py` importing `from pylzt.media import Media` is a one-directional edge
(`media.py` sits at package top level with no imports back into `transport/`).

## 2. `transport/session.py` — `HttpxSession._raw_send` + httpx multipart behavior

**CONFIRMED (current code).** `src/pylzt/transport/session.py:90-99`:

```python
async def _raw_send(self, req: Request) -> Response:
    client = self._client_for(req.proxy)
    headers = {"Authorization": f"Bearer {req.bearer}"} if req.bearer else None
    raw = await client.request(
        req.method,
        req.path,
        params=_flatten_query(req.query) if req.query else None,
        json=req.json_body,
        headers=headers,
    )
```

Only `json=req.json_body` is passed; no `data=`/`files=` today. Matches the plan exactly.

**httpx `data=`+`files=` claim — CONFIRMED, with one real gotcha the plan doesn't mention.**
`httpx.AsyncClient.request()` signature (checked live): `content`, `data`, `files`, `json`,
`params`, `headers`, ... are all independent kwargs — `data=` (dict, form-encoded) and
`files=` (dict, multipart) **can** be passed together and httpx correctly produces one
`multipart/form-data` body containing both the form fields and the file part (verified by
building a real request against `httpx.MockTransport` — body inspected, single boundary,
both `x`/`user_id` form fields and the `avatar` file part present, `content-type:
multipart/form-data; boundary=...`).

Gotcha (🟡, not a blocker): **httpx coerces a `None` value in `data=` to the literal empty
string `""`**, not to "omit the field" (verified: `data={"y": None}` produced a form part
`name="y"` with empty body, not an absent field). This is harmless *only* because
`BaseMethod.build_request` already filters `None`-valued fields out of `rest` before this
point (`methods/base.py:117-119`, `if getattr(self, name) is not None`) — so no `None`
ever reaches `data=` under current code. Worth one sentence in T3's acceptance so a future
change to that filter doesn't silently regress into empty-string form fields.

httpx also auto-coerces non-str scalars (`int`) to their `str()` form in `data=` (verified:
`data={"x": 5}` → form part body `5`) — so the plan's "rest of the fields → `data=`" doesn't
need a manual stringify step.

## 3 / 3b. `methods/base.py` — `BaseMethod.build_request` + pydantic model-field type

**CONFIRMED (current code shape).** `src/pylzt/methods/base.py:74-90, 111-135`:

```python
class BaseMethod[T](BaseModel):
    model_config = ConfigDict(frozen=True)
    __abstract__: ClassVar[bool] = False
    ...

def build_request(self) -> Request:
    values = {
        name: getattr(self, name)
        for name in type(self).model_fields
        if getattr(self, name) is not None
    }
    ...
    return Request(method=..., path=path, rate_class=..., query=query, json_body=body)
```

`BaseMethod` is a **Pydantic v2 `BaseModel`** (frozen via `ConfigDict(frozen=True)`), not a
dataclass — confirms the plan's premise and confirms the `7016a77` migration is in effect
(no dataclass form remains). `build_request` iterates `type(self).model_fields` (a
`dict[str, FieldInfo]`), exactly as the plan assumes. Getting the annotated type to check
"is this field `Media`" is feasible: `type(self).model_fields[name].annotation` gives the
declared type per field (pydantic v2 `FieldInfo.annotation`), so `model_fields[name].annotation
is Media` (or an `issubclass`/Union-aware check if the field is `Media | None`) is a normal,
supported operation — no blocker there.

**Item 3b — the flagged critical check — RESOLVED, NOT a blocker.** The plan worried that a
plain (non-pydantic) `@dataclass(frozen=True, slots=True) class Media` would need
`model_config = ConfigDict(arbitrary_types_allowed=True)` to be usable as a `BaseModel`
field type, citing pydantic v2's general rule that arbitrary non-pydantic classes raise
`PydanticSchemaGenerationError` without that flag.

That general rule is real, but **it does not apply to stdlib dataclasses** — pydantic v2
has first-class native support for generating a core schema from any class satisfying
`dataclasses.is_dataclass()`, independent of `arbitrary_types_allowed`. Verified directly
(sandbox, this environment's installed pydantic — not from memory):

```python
from dataclasses import dataclass
from pydantic import BaseModel

@dataclass(frozen=True, slots=True)
class Media:
    data: bytes
    filename: str
    content_type: str | None = None

class M(BaseModel):
    model_config = {"frozen": True}
    user_id: str
    avatar: Media

m = M(user_id="1", avatar=Media(data=b"x", filename="a.png"))
# -> OK user_id='1' avatar=Media(data=b'x', filename='a.png', content_type=None)
```

This constructs and validates with **no `arbitrary_types_allowed` config at all** — no
`PydanticSchemaGenerationError`. `BaseMethod` subclasses can declare an `avatar: Media` field
today, unmodified, with zero config changes. The plan does not need a step adding
`arbitrary_types_allowed=True` anywhere; if it had included one, it would be harmless-but-
unnecessary, not a fix for a real gap. **This item is the opposite of what the audit prompt
flagged it as — confirmed clean, not a blocker.**

(Caveat for T5/T8 authors: pydantic *does* run its own validation against the dataclass's
own field types when assigning `Media(...)` instances — e.g. it will coerce/validate `data:
bytes` etc. — so unit tests should construct via the real `Media(...)` frozen instance, not
a raw dict, which the plan's `Key types` section already does.)

## 4. `lib/cache.py` / `lib/storage.py` — Null* precedent

**PARTIALLY WRONG location, pattern CONFIRMED elsewhere.** `lib/cache.py` and
`lib/storage.py` themselves contain no `Null*` class — they hold `MemoryCache`
(`lib/cache.py:47-65`) and `MemoryStorage` (`lib/storage.py:70-98`) respectively, both
*stateful* in-process defaults, not no-ops. The `Null*`-style no-op-default precedent the
plan actually needs is real, just filed under different modules:

- `src/pylzt/lib/metrics.py:24` — `class NullMetrics(BaseMetrics)`, all three methods
  (`incr`/`gauge`/`observe`) `return None`.
- `src/pylzt/proxy_pool/sticky.py:101` — `class NullProxyPool(BaseProxyPool)`, docstring
  "No-op pool used when proxy support is disabled; always yields None."

Both are wired as `Client.__init__` defaults (`client.py:96` `metrics or NullMetrics()`;
`client.py:105-109` `NullProxyPool()` when no `proxy_source`). So the plan's decision-log
claim "`NullMetrics`/`NullProxyPool`-style opt-in-only defaults are the established
convention" is **substantively correct**, but its `verified-by-code:src/pylzt/lib/cache.py`
citation points at the wrong file — the citation should read
`verified-by-code:src/pylzt/lib/metrics.py:24` and
`src/pylzt/proxy_pool/sticky.py:101`. 🟡 fix the citation, not the design decision.

## 5. `client.py` — insertion point for `media_storage.save()`

**CONFIRMED, clean insertion point exists.** Full call chain traced:

- `Client.__init__` (`client.py:79-122`) — exact signature confirmed: `tokens`, `transport`,
  `forum_transport`, `token_pool`, `proxy_source`, `retry`, `metrics`, `clock`,
  `category_cache`, `batch_storage`, `config` (keyword-only after `tokens`). Adding
  `media_storage: BaseMediaStorage | None = None` as one more keyword-only param with a
  `self._media_storage = media_storage or NullMediaStorage()` line follows the exact same
  pattern as every other optional collaborator (`metrics or NullMetrics()`, `retry or
  ExponentialBackoff()`) — mechanically trivial, no special-casing needed.
- `Client.execute` (`client.py:329-331`):
  ```python
  async def execute[T](self, method: BaseMethod[T]) -> T:
      return self._bind(await method(self._transport_for(method)))
  ```
- `BaseMethod.__call__` (`methods/base.py:162-163`) — **exists, confirmed** (the plan
  correctly assumed it but didn't quote it):
  ```python
  async def __call__(self, transport: BaseTransport) -> T:
      return self.parse_response(await transport.send(self.build_request()))
  ```
  This is where `transport.send()` actually fires and where the parsed `T` becomes
  available, all *inside* the `await method(...)` expression in `execute()`.

Consequence for T6: by the time `execute()`'s `await method(...)` resolves, the HTTP call
has already succeeded (an error response raises inside `_raw_send` via `LztError.match`,
never reaching this point) and `self` (the `BaseMethod` instance, still holding the
original `Media`-typed field values since `BaseModel` fields are unaffected by
`build_request`) is available in `execute`'s own scope via the `method` parameter. So T6's
acceptance ("after execute() of a method carrying a Media field, media_storage.save() is
called") is directly implementable as:

```python
async def execute[T](self, method: BaseMethod[T]) -> T:
    result = await method(self._transport_for(method))
    self._save_media_best_effort(method)  # iterates method's own Media-typed fields
    return self._bind(result)
```

No new plumbing is needed to get from "successful execute" to "the Media instance" — it's
already sitting on `method`, the parameter `execute` already has. Plan's T6 is implementable
exactly as claimed.

## 6. `methods/forum_users.py` — field lists

**CONFIRMED, exact match.** All four classes read in full:

- `UsersAvatarUpload(BaseMethod[str])` — field list: `user_id: str`. Nothing else.
- `UsersAvatarCrop(BaseMethod[str])` — fields: `user_id: str`, `x: int | None = None`,
  `y: int | None = None`, `crop: int | None = None`.
- `UsersBackgroundUpload(BaseMethod[str])` — field list: `user_id: str`. Nothing else.
- `UsersBackgroundCrop(BaseMethod[str])` — fields: `user_id: str`, `x/y/crop: int | None =
  None` (same shape as the avatar crop).

Matches the plan's claim precisely: uploads have only `user_id` (no file field at all today
— uploads are indeed currently impossible through this SDK, as the plan's Goal states), crops
add `x`/`y`/`crop` and nothing else.

## 7. `dev/codegen/generator.py` — no existing binary/multipart handling

**CONFIRMED.** Case-insensitive search for `binary` → no matches. `multipart` → no matches.
`format` → 5 matches, all belonging to `_format_docstring()` (a docstring-rendering helper,
generator.py:603/664/1284) or `.format(T=...)` string templating for generic type params
(generator.py:925/1109) — none related to OpenAPI `format: "binary"` request-body detection
or multipart encoding. T7 is additive work with no prior partial implementation to reconcile
against.

## Verdict

**No 🔴 blocker.** Item 3b — the item explicitly flagged as the most likely blocker — is
**resolved clean**: pydantic v2 natively schemas stdlib dataclasses as `BaseModel` field
types, so `Media` needs no `arbitrary_types_allowed` config change, contrary to the concern
raised. All other structural claims (Request shape, `_raw_send` behavior, `build_request`
iteration, `BaseMethod`'s pydantic nature, `__call__`/`execute` call chain, the four upload
method field lists, absence of prior codegen binary/multipart handling) are confirmed
correct against live source.

Two 🟡 minor corrections to make before/while executing the plan:

1. **Citation fix** (item 4): the plan's `verified-by-code:src/pylzt/lib/cache.py` for the
   `NullMetrics`/`NullProxyPool` precedent points at the wrong file. Correct citations are
   `src/pylzt/lib/metrics.py:24` (`NullMetrics`) and `src/pylzt/proxy_pool/sticky.py:101`
   (`NullProxyPool`). The design decision itself (Null-object default, not
   `MemoryStorage`-style stateful default) stands.
2. **httpx `None`-coercion note** (item 2): add one sentence to T3's acceptance criteria
   documenting that httpx's `data=` turns a `None` value into an empty-string form field
   rather than omitting it — currently harmless only because `build_request` already strips
   `None` fields before they reach `data=`; flag it so a future refactor of that filter
   doesn't silently reintroduce empty-string fields sent to the live API.

Plan is implementation-ready as written, modulo those two citation/documentation fixes.

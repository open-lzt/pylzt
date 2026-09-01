# Why 42 endpoints are still `passthrough`, and what typing them costs

Measured 01.09.2026 on `dev/generated/openapi/*.json` (404 upstream methods, 289 routable).

## The defect

`_is_object()` required `"type": "object"`:

```python
return schema.get("type") == "object" and bool(schema.get("properties"))
```

**47 of this spec's 200-responses carry `properties` and omit `type`** — legal JSON Schema,
`type` is optional. They fell through to the scalar branch, so the method shipped
`__returning__ = passthrough`.

```
CategoriesGet  /categories/{category_id}
  {"properties": {"category": {"$ref": ".../CategoryModel"}, ...}, "required": [...]}
```

Breakdown of the 66 `Passthrough` methods against the spec:

| bucket | count | typable |
|---|---|---|
| object schema with no `type` | 47 | yes — the defect above |
| response is an array / scalar / one-field unwrap | 18 | no, `passthrough` is correct |
| not in the spec at all | 1 | needs a live capture |

## The fix, and its price

One predicate. Measured by generating into the staging tree twice and diffing:

- **42 methods go `passthrough` → typed**
- **0 methods regress to `passthrough`**
- **12 published model names disappear**, 3 keep their name with a different field count
- `User` (49 fields) is renamed to `ListUser`, and a **new 3-field shape takes the name `User`**

The last line is the blocker: an importer of `User` keeps compiling and gets a different
model. Nothing warns.

## Why the name moves at all

Model names are assigned from a global pool in declaration order (`_build_model` interning,
then the generic fold and the neutral-name pass). Adding 42 response shapes reshuffles which
shape wins each name. The naming is **order-dependent, not identity-dependent**.

## Pinning by field set was tried and is wrong

Reserving each published name for its published field-name set made the diff worse:
**69 renames instead of 4**, many carrying the numeric suffixes the generator is supposed never
to emit (`PublicCountLinesResponse2`). Reason: a response whose own shape drifted slightly can
no longer claim its own name, because the old field set holds it.

The stable identity of a response model is **the operation that returns it**, not its fields.
Pinning has to key on the method class, and that is a change to the naming pass, not a guard in
front of it.

## `__returning__` is not the whole declaration

Found the same day from the consumer side: `GetLot` is hand-written, owns `parse_response`,
leaves `__returning__` at `None` and states its type as `BaseMethod[Lot]`. Anything reading only
`__returning__` files it as untyped — the testnet stand did, and answered `{}`, which
`Lot.from_raw` accepts. Its client smoke test asserted a parsed lot against an empty body and
passed for as long as the stand stayed quiet about it.

Two methods are in that shape today (`GetLot`, `GetSelfProfile`). A consumer that needs the
response type must read `__returning__` first and fall back to the generic argument.

## State

The `_is_object` fix lives on `fix/typeless-object-schemas`, generated and diffed, **not
installed**. Installing it is a breaking release of the model namespace and needs a version
decision.

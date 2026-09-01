# Changelog

## 0.3.0

**Breaking: 10 response models are gone and 3 changed shape under the same name.** Check the
table below before upgrading; nothing else in the public surface moved.

### 42 more endpoints return a typed model

`_is_object()` in the generator required `"type": "object"`. JSON Schema makes `type` optional,
and 47 of the spec's 200-responses omit it — those fell to the scalar branch and shipped
`__returning__ = passthrough`. Untyped methods went from 66 to 24.

`CategoriesGet`, `ConversationsGet`, `ForumsFollowed`, `PostsList`, `PostsLikes` and 37 others
now return a model instead of the raw body.

### A generated model may no longer be named `Field`

A wire field named `field` produced `class Field`, which shadowed `pydantic.Field` in its own
module — `Field(alias=...)` on the next line called the model and raised at import. Names that
collide with the generator's own imports get a `Model` suffix (`FieldModel`).

### Model names are pinned to the operation that publishes them

Names come from one global pool in declaration order, so adding 42 response shapes reshuffled
which shape won each name — `User` (48 fields) was about to become `ListUser` while a new
3-field shape took `User`. A final pass now gives every operation back the model name it already
publishes, and a shape new to this run yields the name instead.

Pinning by field set was tried first and made it worse (69 renames, with the numeric suffixes
this generator never emits). The stable identity of a response model is the operation that
returns it, not its fields. Measurement: `docs/decisions/passthrough-and-model-names.md`.

### Removed models

| gone | why |
|---|---|
| `UsersListResponse` | folded into the generic `UsersResponse[User]` |
| `UserField` · `UserProfileThread` · `UserUserGroup` · `UserUserFollowing` · `UserUserExternalAuthentication` · `UserEditPermissions` | nested shapes that no longer occur under `User` |
| `ProfilePostsCommentsEditCommentLinks` · `ProfilePostsCommentsEditCommentPermissions` | `ProfilePostsCommentsEdit` shares `ProfilePostsCommentsCreateComment` and its nested pair |
| `SearchAllPermissionsBump` | replaced by the shared `PermissionsBump` shape |
| `CategoryItemSeller` | the shape is Battle.net-specific; now `CategoryBattleNetItemSeller` |

### Changed shape, same name

| model | fields before | after |
|---|---|---|
| `Notification` | 4 | 13 |
| `UserLinks` | 12 | 10 |
| `UserPermissions` | 6 | 5 |

### Still untyped

24 methods keep `passthrough`: their response is an array, a scalar, or a one-field unwrap, where
`passthrough` is correct. One (`CategoryParams`) is absent from the spec entirely and needs a
live capture.

`__returning__` is not the only declaration — a hand-written method that owns `parse_response`
states its type as the generic argument of `BaseMethod[Lot]` (`GetLot`, `GetSelfProfile`). A
consumer reading response types must check both.

<p align="right"><b>English</b> · <a href="README.md">Русский</a></p>

<div align="center">

# pylzt

<sub>Typed async framework over the lzt.market / lolzteam / AntiPublic APIs — not a thin HTTP wrapper</sub>

[![CI](https://github.com/open-lzt/pylzt/actions/workflows/ci.yml/badge.svg)](https://github.com/open-lzt/pylzt/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-2a6db2)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/badge/lint-ruff-d7ff64)](https://docs.astral.sh/ruff/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

[Full documentation](docs/) · [AI-agent docs](docs/for_ai/)

Typed async **framework** over the [lzt.market](https://lzt.market) marketplace API,
the [lolzteam](https://lolz.live) forum API, and the [AntiPublic](https://antipublic.one)
leak-checking API — not a thin HTTP wrapper.

**[Why a framework](#why-a-framework-not-a-library)** ·
**[Quickstart](#quickstart)** ·
**[Sync](#sync-without-await)** ·
**[Mock](#against-the-mock-lzt-testnet)** ·
**[Pagination](#pagination)** ·
**[Batching](#batching-n-calls-into-one-request)** ·
**[Media uploads](#uploading-media)** ·
**[AntiPublic](#antipublic-leak-checking-api)** ·
**[Errors](#error-handling)** ·
**[Codegen](#codegen-the-builder)**

## Why a framework, not a library

A wrapper gives you typed methods over an HTTP client. pylzt ships the operational
machinery a production integration actually needs, already wired together:

- **Token pool** (`token_pool/round_robin.py`) — round-robins over many marketplace
  tokens, each metered by its own per-`RateClass` bucket at the official published
  ceilings (Market 120/min general + 20/min Category Search; Forum 300/min). AntiPublic
  gets its own single-credential pool (`token_pool/_static.py`) — a license key isn't
  fungible with an OAuth token, so it never enters the same rotation.
- **Proxy pool** (`proxy_pool/`) — sticky-per-token or round-robin egress proxies
  (HTTP/HTTPS/SOCKS5) with per-proxy circuit-breaker health tracking.
- **Resilience** (`transport/base.py`, `lib/retry.py`) — retry with jittered
  backoff honoring `Retry-After`, a typed self-registering error hierarchy
  (`errors.py`), request-coalescing `/batch` (`lib/batch.py`), a TTL cache honoring the
  server's `cacheTTL`.
- **Method-as-class** (`methods/base.py`) — every endpoint is a frozen `BaseMethod[T]`
  Pydantic model, not a hand-maintained function — malformed request fields fail at
  construction, not on the wire; `Client.execute(method)` is the one request-execution
  path every domain namespace and every generated facade method delegates to.
- **Generated, not hand-transcribed** (`dev/codegen/`) — methods, response models,
  enums, and facades are generated from the official OpenAPI reference, flat into the
  library behind a ruff+mypy gate. Auto-detects `format: binary` fields into a real
  `Media` type, so file-upload endpoints get typed multipart support for free.
- **Sync and async, one engine** (`sync/runner.py`) — `SyncClient` isn't a second
  implementation of rate limiting and retries; it runs the *same* async engine on a
  background event-loop thread (`SyncRunner`), with every method's return type
  matching its async counterpart's unwrapped type under `mypy --strict`.

## Quickstart

```bash
pip install "git+https://github.com/open-lzt/pylzt.git"
```

```python
import asyncio

from pylzt import Client
from pylzt.types import Category


async def main() -> None:
    async with Client.from_token("<market-token>") as client:  # or Client.from_env() from $LZT_TOKEN
        lot = await client.market.get_lot(item_id=42)
        print(lot.item_id, lot.price, lot.title)

        async for lot in client.market.list_lots(category=Category.STEAM):
            print(lot.item_id, lot.price)


asyncio.run(main())
```

`client.market` / `client.forum` / `client.antipublic` are the three domain
namespaces — every endpoint in the official spec is a real method on the matching
one (`client.forum.threads_get(...)`, `client.antipublic.license_check_license()`).

## Sync without `await`

```python
from pylzt.sync.client import SyncClient

with SyncClient("<market-token>") as client:
    lot = client.market.get_lot(item_id=42)
```

## Against the mock (lzt-testnet)

```python
from pylzt import Client, ClientConfig

async with Client.from_token("t", config=ClientConfig.for_testnet()) as client:
    ...  # every call hits the local mock at 127.0.0.1:8765
```

## Pagination

```python
from decimal import Decimal
from pylzt.types import Category, OrderBy

# stream page by page (max_pages is an optional cap)
async for lot in client.market.list_lots(category=Category.STEAM, order_by=OrderBy.PRICE_ASC, max_pages=5):
    ...

all_lots = await client.market.list_lots(category=Category.STEAM, pmax=Decimal("500")).collect(limit=200)
first = await client.market.list_lots(category=Category.STEAM).first_page()
```

## Batching N calls into one request

Three ways in, pick by how the calls arise in your code:

```python
from pylzt.methods.catalog import GetLot
from pylzt.methods.categories import CategoryParams
from pylzt.types import Category, ItemId

# 1. You already have the full list up front — one POST /batch, one call.
results = await client.execute_batch([
    GetLot(item_id=ItemId(1)),
    CategoryParams(category=Category.STEAM),
])

# 2. Calls are scattered across a function/loop — wrap the region, every execute()
#    inside coalesces into /batch requests instead of firing one per call.
async with client.batching():
    lot, categories = await asyncio.gather(
        client.execute(GetLot(item_id=ItemId(1))),
        client.execute(CategoryParams(category=Category.STEAM)),
    )

# 3. No block to wrap (e.g. calls originate in unrelated call sites) — job() coalesces
#    with every other concurrent job() call through one shared, client-lifetime collector.
lot = await client.job(GetLot(item_id=ItemId(1)))
```

## Uploading media

```python
from pylzt import Media

avatar = Media.from_path("avatar.png")
await client.forum.users_avatar_upload(user_id="me", avatar=avatar)
```

See [`docs/integration-guide.md`](docs/integration-guide.en.md) for `media_storage=`
(an optional post-upload byte cache).

## AntiPublic (leak-checking API)

A separate license key, not a market/forum token — it never enters the same rotation
(see the framework overview above):

```python
async with Client.from_token("<market-token>", antipublic_key="<antipublic-license-key>") as client:
    remaining = await client.antipublic.license_available_queries()
    hit = await client.antipublic.license_check_lines(lines=("user:pass",))
```

Calling `client.antipublic.*` without `antipublic_key=` raises `CredentialMissing` —
fail loud instead of a silent no-op.

## Error handling

Every failure the SDK raises is an `LztError` subclass — catch the specific type
you can recover from, and let the rest propagate:

```python
from pylzt import AuthFailed, NotFound, RateLimited, TransportError
from pylzt.types import ItemId

try:
    lot = await client.market.get_lot(item_id=ItemId(999_999_999))
except NotFound:
    ...  # lot doesn't exist or isn't visible to this token
except RateLimited as exc:
    ...  # exc carries retry_after — the token pool already backs off internally
except AuthFailed:
    ...  # token is dead/revoked — pull it out of rotation, see reconfigure()
except TransportError:
    ...  # upstream 5xx after retries were exhausted
```

Full walkthrough — DI, config, fakes for tests, `reconfigure()` for live token
rotation, the full error table: **[`docs/integration-guide.md`](docs/integration-guide.en.md)**.

## Codegen (the builder)

The SDK's methods, response models, enums and facades are generated from the
official readme.io OpenAPI reference and installed **flat** into the library behind a
ruff + mypy gate. `dev/codegen/` (`pipeline.py` + `generator.py` + `scraper.py`, driven by
`python -m dev.codegen`) is two-phase: `generate` renders into a staging tree and never
touches the library; `install` promotes staging into `src/pylzt/` behind the gate and
rolls back on any failure, so the library on disk is never left broken by a regen.

### Commands

```bash
python -m dev.codegen generate                 # render into dev/codegen/generated/ only
python -m dev.codegen install                  # promote staging -> library, behind the gate
python -m dev.codegen build                     # generate + install in one shot (the common case)
python -m dev.codegen build --scrape            # re-scrape the OpenAPI spec first, then build
python -m dev.codegen scrape                    # scrape + merge the spec only, no codegen
python -m dev.codegen check                     # run the ruff + mypy + import gate, no regen
```

Useful flags (repeatable, combine freely):

| Flag | On | Effect |
|---|---|---|
| `--api market` / `--api forum` / `--api antipublic` | `generate`, `build` | restrict to one API (repeatable); default: all three |
| `--scrape` | `generate`, `build` | re-fetch the readme.io reference before rendering |
| `--refresh` | `generate --scrape`, `build --scrape`, `scrape` | ignore the on-disk page cache, refetch every page |
| `--model-backend {pydantic,dataclass}` | `generate`, `build` | response-DTO target; default `pydantic` (request methods are always frozen Pydantic models) |
| `--no-validate` | `install`, `build` | skip the ruff+mypy gate on install (danger — only for a quick local look at staged output) |
| `--site market` / `--site forum` / `--site antipublic` | `scrape` | restrict scraping to one site (repeatable) |

### What each phase does

- **`scraper.py`** fetches every readme.io reference page for a site and unions the
  embedded OpenAPI 3.1 fragments into one merged spec, cached per-page on disk under
  `dev/generated/openapi/.page_cache/<site>/` (`--refresh` bypasses the cache). The merged
  spec is written to `dev/generated/openapi/lzt_<site>.json` — **these JSON files are
  versioned** (see below); the page cache and scrape logs next to them are not.
- **`generator.py`** turns that spec into typed method-classes (`BaseMethod[T]`), nested
  Pydantic response models, `StrEnum`s, async facade methods, and a parallel **sync**
  facade per site (`facades/sync_{api}.py` — each method a thin blocking wrapper over
  its async counterpart via `SyncRunner`, no second spec-derived implementation) — flat
  into `dev/codegen/generated/{methods,models,enums,facades}/`. It also runs a
  normalisation pass over the raw extraction so the output stays hand-written-quality
  rather than a literal 1:1 spec dump — folding structurally-identical models into one
  class, hoisting shared generic bases, mapping `format: binary` request fields to the
  real `Media` type, and **reusing hand-written primitives instead of duplicating
  them**: any enum whose wire values are `{yes, no, nomatter}` (or a subset) collapses onto
  the one `pylzt.types.Tristate` — with a `Tristate.from_bool(value: bool | None)`
  classmethod — instead of a same-shaped duplicate class per field name (`Tel`, `EditBtag`,
  `ClashPass`, ...); any response model whose leading field is `status: str` rebases onto
  `pylzt.models.base.BaseResponse`, which owns `is_ok()`, instead of every model carrying
  its own copy of that field. `EXISTING_TYPES_ENUMS` in `generator.py` is the full list of
  hand-written enums codegen imports rather than regenerates.
- **`pipeline.py`** snapshots the currently-installed generated files, wipes them (so a
  removed domain's file disappears on the next build), copies the staged set in, runs
  `ruff --fix` then the ruff+mypy+import gate, and restores the snapshot on any failure.

Generated and hand-written modules coexist flat in the same package — generated ones carry
an auto-gen header marker and an `{api}_` / `{api}` name, hand-written ones are unprefixed,
and `install` refuses to overwrite a hand-written module (`_guard_no_clobber`). See
`dev/codegen/_MODULE.md` for the full contract.

### API schema

`dev/generated/openapi/lzt_market.json`, `lzt_forum.json`, and `lzt_antipublic.json` —
the merged OpenAPI specs `scraper.py` produces — are committed so a clone can
`python -m dev.codegen build` without re-scraping readme.io first. Everything else under
`dev/generated/` (the page cache, scrape logs, and `dev/codegen/generated/` staging tree)
stays gitignored and gets rebuilt on demand. Re-scrape with
`python -m dev.codegen scrape --refresh` when the upstream reference changes, and commit
the updated JSON files alongside the codegen diff they produce.

### Live verification

Every generated file carries a `Generated by forge — DO NOT EDIT` docstring — the
spec's declared types don't always match what the API actually returns, so a fresh
regen is never a place to hand-patch. `tests/pylzt/e2e/test_live_read.py` (marker
`e2e`, needs `LZT_E2E_TOKEN`, excluded from the default test run) auto-discovers and
exercises every zero-argument GET endpoint against the real API. See
**`docs/codegen-runbook.md`** for what's been verified, what's
still known-broken, and the hand-patch mechanism for fixing a spec/reality mismatch
without the next codegen run silently reverting it.

## Development

GitHub Actions is unavailable on this account (locked pending a payment method), so
`.github/workflows/ci.yml` is not a working gate today. `.githooks/pre-push` mirrors it
locally (ruff check, ruff format --check, mypy, pytest) and blocks a push on failure.
After cloning, point git at it once: `git config core.hooksPath .githooks`.

## Contributing

```bash
git clone https://github.com/open-lzt/pylzt && cd pylzt
uv sync --extra dev
git config core.hooksPath .githooks   # local ruff+mypy+pytest gate on push, see above
uv run pytest -q
```

PRs go against `main`. `.githooks/pre-push` is the actual gate right now (see
Development above) — it must pass before a push goes through.

## Authors

- [zlexdev](https://github.com/zlexdev)

## License

[MIT](LICENSE).

<p align="right"><b>English</b> · <a href="README.md">Русский</a></p>

<div align="center">

# pylzt

<sub>Typed async framework over the lzt.market / lolzteam / AntiPublic APIs — not a thin HTTP wrapper</sub>

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-2a6db2)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/badge/lint-ruff-d7ff64)](https://docs.astral.sh/ruff/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

[Documentation](docs/) · [AI-agent docs](docs/for_ai/) · [Integration guide](docs/integration-guide.md)

## Install

```bash
pip install pylzt
```

Unreleased `main` instead of a release — `pip install "git+https://github.com/open-lzt/pylzt.git"`.

Python 3.12+. Dependencies: `pydantic>=2.7`, `httpx[socks]>=0.27`, `structlog>=24.1`.

## Quickstart

```python
import asyncio

from pylzt import Client
from pylzt.models.lot import LotFilter
from pylzt.types import Category


async def main() -> None:
    async with Client(["<market-token>"]) as client:
        lot = await client.market.get_lot(item_id=42)
        print(lot.item_id, lot.price, lot.title)

        async for lot in client.market.list_lots(LotFilter(category=Category.STEAM)):
            print(lot.item_id, lot.price)


asyncio.run(main())
```

Three domain namespaces: `client.market` · `client.forum` · `client.antipublic`. Every endpoint in the official spec is a real method on the matching one (`client.forum.threads_get(...)`, `client.antipublic.license_check_license()`).

Tokens don't have to go through the constructor — they're read from `LZT_TOKENS`.

## Sync and async, one engine

`SyncClient` is not a second implementation of rate limiting and retries. It runs the same async engine on a background event-loop thread (`sync/runner.py`), and its return types match the async ones under `mypy --strict`.

```python
async with Client(["<market-token>"]) as client:
    lot = await client.market.get_lot(item_id=42)

from pylzt.sync.client import SyncClient

with SyncClient(["<market-token>"]) as client:
    lot = client.market.get_lot(item_id=42)   # no await
```

## Pagination

```python
from decimal import Decimal

from pylzt.models.lot import LotFilter
from pylzt.types import Category, OrderBy

filt = LotFilter(category=Category.STEAM, pmax=Decimal("500"), order_by=OrderBy.PRICE_ASC)

async for lot in client.market.list_lots(filt, max_pages=5):
    ...

all_lots = await client.market.list_lots(filt).collect(limit=200)   # materialize
first = await client.market.list_lots(filt).first_page()            # first page only
```

## Batching N calls into one request

Three entry points — pick by how the calls arise in your code.

```python
from pylzt.methods.catalog import GetLot
from pylzt.methods.categories import CategoryParams
from pylzt.types import Category, ItemId

# 1. The full list is known up front — one POST /batch.
results = await client.execute_batch([
    GetLot(item_id=ItemId(1)),
    CategoryParams(category=Category.STEAM),
])

# 2. Calls are scattered across a function — wrap the region, and every execute()
#    inside coalesces into /batch instead of firing one request per call.
async with client.batching():
    lot, categories = await asyncio.gather(
        client.execute(GetLot(item_id=ItemId(1))),
        client.execute(CategoryParams(category=Category.STEAM)),
    )

# 3. Nothing to wrap (calls originate in unrelated places) — job() coalesces with
#    every other concurrent job() through one client-lifetime collector.
lot = await client.job(GetLot(item_id=ItemId(1)))
```

## Uploading media

```python
from pylzt import Media

avatar = Media.from_path("avatar.png")
await client.forum.users_avatar_upload(user_id="me", avatar=avatar)
```

An optional post-upload byte cache — `media_storage=`, see the [integration guide](docs/integration-guide.md).

## AntiPublic

A separate license key, not a market token — it never enters the same rotation.

```python
async with Client(["<market-token>"], antipublic_key="<antipublic-license-key>") as client:
    remaining = await client.antipublic.license_available_queries()
    hit = await client.antipublic.license_check_lines(lines=("user:pass",))
```

Calling `client.antipublic.*` without `antipublic_key=` raises `CredentialMissing` — fail loud instead of a silent no-op.

## Errors

Everything the SDK raises is an `LztError` subclass. Catch the type you can recover from and let the rest propagate.

```python
from pylzt import AuthFailed, NotFound, RateLimited, TransportError
from pylzt.types import ItemId

try:
    lot = await client.market.get_lot(item_id=ItemId(999_999_999))
except NotFound:
    ...  # no such lot, or not visible to this token
except RateLimited as exc:
    ...  # exc.retry_after — the token pool already backed off
except AuthFailed:
    ...  # dead token — pull it from rotation, see reconfigure()
except TransportError:
    ...  # upstream 5xx, retries exhausted
```

The full error table, DI, fakes for tests, `reconfigure()` for live token rotation — [`docs/integration-guide.md`](docs/integration-guide.md).

## Why a framework, not a library

A wrapper gives you typed methods over an HTTP client. pylzt ships the operational machinery a production integration actually needs, already wired together:

- **Token pool** (`token_pool/round_robin.py`) — round-robins over many tokens, each metered by its own per-`RateClass` bucket at the official published ceilings (Market 120/min + 20/min Category Search, Forum 300/min). AntiPublic gets its own single-credential pool (`token_pool/_static.py`).
- **Proxy pool** (`proxy_pool/`) — sticky-per-token or round-robin, HTTP/HTTPS/SOCKS5, per-proxy circuit breaker.
- **Resilience** (`transport/base.py`, `lib/retry.py`) — jittered retry honoring `Retry-After`, a self-registering typed error hierarchy, request coalescing into `/batch`, a TTL cache honoring the server's `cacheTTL`.
- **Method-as-class** (`methods/base.py`) — every endpoint is a frozen `BaseMethod[T]` Pydantic model. Malformed request fields fail at construction, not on the wire. `Client.execute(method)` is the single request-execution path behind every facade.
- **Generated, not hand-transcribed** (`dev/codegen/`) — methods, response models, enums and facades are rendered from the official OpenAPI reference behind a ruff+mypy gate. `format: binary` becomes a real `Media` type automatically.

## Codegen

Two phases: `generate` renders into a staging tree and never touches the library, `install` promotes staging into `src/pylzt/` behind the gate and rolls back on failure. The library on disk is never left broken by a regen.

```bash
python -m dev.codegen build            # generate + install, the common case
python -m dev.codegen build --scrape   # re-scrape the spec first
python -m dev.codegen generate         # render into dev/codegen/generated/ only
python -m dev.codegen install          # promote staging → library only
python -m dev.codegen scrape           # scrape + merge the spec only
python -m dev.codegen check            # ruff+mypy+import gate only, no regen
```

| Flag | On | Effect |
|---|---|---|
| `--api market\|forum\|antipublic` | `generate`, `build` | restrict to one API (repeatable); default all three |
| `--scrape` | `generate`, `build` | re-fetch the readme.io reference before rendering |
| `--refresh` | `*--scrape`, `scrape` | ignore the on-disk page cache |
| `--model-backend {pydantic,dataclass}` | `generate`, `build` | response-DTO target; default `pydantic` |
| `--no-validate` | `install`, `build` | skip the gate (dangerous, local inspection only) |
| `--site market\|forum\|antipublic` | `scrape` | restrict scraping to one site |

The merged specs `dev/generated/openapi/lzt_{market,forum,antipublic}.json` are **committed**, so a fresh clone builds without scraping. Everything else under `dev/generated/` is gitignored.

Every generated file carries `Generated by forge — DO NOT EDIT`: the spec doesn't always match what the API actually returns, and a regen would wipe a hand patch. What's been verified live, what's known-broken, and how to patch a spec/reality mismatch — [`docs/codegen-runbook.md`](docs/codegen-runbook.md).

## Development

```bash
git clone https://github.com/open-lzt/pylzt && cd pylzt
uv sync --extra dev
git config core.hooksPath .githooks   # local ruff+mypy+pytest gate on push
uv run pytest -q
```

E2E tests hit the live API, need `LZT_E2E_TOKEN` and are excluded from the default run:

```bash
uv run pytest -m e2e -q
```

GitHub Actions is unavailable on this account, so the real gate today is `.githooks/pre-push`. It blocks a push on failure.

## Ecosystem

[lzt-testnet](https://github.com/open-lzt/lzt-testnet) — mock market for tests · [lzt-eventus](https://github.com/open-lzt/lzt-eventus) — event engine · [auto-lzt](https://github.com/open-lzt/auto-lzt) — no-code automation · [lzt-mcp](https://github.com/open-lzt/lzt-mcp) — server for AI agents · [the whole stand](https://github.com/open-lzt/open-lzt)

## License

[MIT](LICENSE)

<p align="right"><a href="README.en.md">English</a> · <b>Русский</b></p>

<div align="center">

# pylzt

<sub>Типизированный async-фреймворк над API lzt.market / lolzteam / AntiPublic — не тонкая обёртка над HTTP</sub>

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-2a6db2)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/badge/lint-ruff-d7ff64)](https://docs.astral.sh/ruff/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

[Документация](docs/) · [Для AI-агентов](docs/for_ai/) · [Гайд по интеграции](docs/integration-guide.md)

## Установка

```bash
pip install pylzt
```

Свежий `main` вместо релиза — `pip install "git+https://github.com/open-lzt/pylzt.git"`.

Python 3.12+. Зависимости: `pydantic>=2.7`, `httpx[socks]>=0.27`, `structlog>=24.1`.

## Быстрый старт

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

Три доменных неймспейса: `client.market` · `client.forum` · `client.antipublic`. Каждый эндпоинт официальной спеки — реальный метод на своём неймспейсе (`client.forum.threads_get(...)`, `client.antipublic.license_check_license()`).

Токены можно не передавать в конструктор — они читаются из `LZT_TOKENS`.

## Sync и async — один движок

`SyncClient` — не вторая реализация рейт-лимитов и ретраев. Он крутит тот же async-движок на фоновом потоке с event-loop (`sync/runner.py`), и типы возврата совпадают с async-аналогами под `mypy --strict`.

```python
async with Client(["<market-token>"]) as client:
    lot = await client.market.get_lot(item_id=42)

from pylzt.sync.client import SyncClient

with SyncClient(["<market-token>"]) as client:
    lot = client.market.get_lot(item_id=42)   # без await
```

## Пагинация

```python
from decimal import Decimal

from pylzt.models.lot import LotFilter
from pylzt.types import Category, OrderBy

filt = LotFilter(category=Category.STEAM, pmax=Decimal("500"), order_by=OrderBy.PRICE_ASC)

async for lot in client.market.list_lots(filt, max_pages=5):
    ...

all_lots = await client.market.list_lots(filt).collect(limit=200)   # в список
first = await client.market.list_lots(filt).first_page()            # только первая страница
```

## Батчинг N вызовов в один запрос

Три входа — выбирайте по тому, как вызовы возникают в вашем коде.

```python
from pylzt.methods.catalog import GetLot
from pylzt.methods.categories import CategoryParams
from pylzt.types import Category, ItemId

# 1. Список известен заранее — один POST /batch.
results = await client.execute_batch([
    GetLot(item_id=ItemId(1)),
    CategoryParams(category=Category.STEAM),
])

# 2. Вызовы разбросаны по функции — оберните участок, каждый execute() внутри
#    склеится в /batch вместо отдельного запроса.
async with client.batching():
    lot, categories = await asyncio.gather(
        client.execute(GetLot(item_id=ItemId(1))),
        client.execute(CategoryParams(category=Category.STEAM)),
    )

# 3. Оборачивать нечего (вызовы из несвязанных мест) — job() склеивает со всеми
#    другими параллельными job() через общий сборщик на время жизни клиента.
lot = await client.job(GetLot(item_id=ItemId(1)))
```

## Загрузка файлов

```python
from pylzt import Media

avatar = Media.from_path("avatar.png")
await client.forum.users_avatar_upload(user_id="me", avatar=avatar)
```

Опциональный кэш байтов после загрузки — `media_storage=`, см. [гайд по интеграции](docs/integration-guide.md).

## AntiPublic

Отдельный лицензионный ключ, не токен маркета — в общую ротацию он не попадает никогда.

```python
async with Client(["<market-token>"], antipublic_key="<antipublic-license-key>") as client:
    remaining = await client.antipublic.license_available_queries()
    hit = await client.antipublic.license_check_lines(lines=("user:pass",))
```

Вызов `client.antipublic.*` без `antipublic_key=` поднимает `CredentialMissing` — падаем громко, а не молча ничего не делаем.

## Ошибки

Всё, что поднимает SDK, — подклассы `LztError`. Ловите тот тип, от которого умеете восстанавливаться, остальное пусть летит выше.

```python
from pylzt import AuthFailed, NotFound, RateLimited, TransportError
from pylzt.types import ItemId

try:
    lot = await client.market.get_lot(item_id=ItemId(999_999_999))
except NotFound:
    ...  # лота нет или он не виден этому токену
except RateLimited as exc:
    ...  # exc.retry_after — пул токенов уже отступил сам
except AuthFailed:
    ...  # токен мёртв — убрать из ротации, см. reconfigure()
except TransportError:
    ...  # upstream 5xx, ретраи исчерпаны
```

Полная таблица ошибок, DI, фейки для тестов, `reconfigure()` для горячей ротации токенов — [`docs/integration-guide.md`](docs/integration-guide.md).

## Почему фреймворк, а не библиотека

Обёртка даёт типизированные методы над HTTP-клиентом. pylzt даёт операционную обвязку, которая нужна боевой интеграции, уже собранную:

- **Пул токенов** (`token_pool/round_robin.py`) — round-robin по многим токенам, каждый со своим ведром на `RateClass` по официальным потолкам (Market 120/мин + 20/мин Category Search, Forum 300/мин). У AntiPublic свой пул на одну учётку (`token_pool/_static.py`).
- **Пул прокси** (`proxy_pool/`) — sticky-per-token или round-robin, HTTP/HTTPS/SOCKS5, circuit breaker на каждый прокси.
- **Устойчивость** (`transport/base.py`, `lib/retry.py`) — ретраи с джиттером и уважением `Retry-After`, самрегистрирующаяся типизированная иерархия ошибок, склейка запросов в `/batch`, TTL-кэш по серверному `cacheTTL`.
- **Метод как класс** (`methods/base.py`) — каждый эндпоинт это frozen `BaseMethod[T]` на Pydantic. Кривое поле запроса падает при конструировании, а не на проводе. `Client.execute(method)` — единственный путь исполнения запроса для всех фасадов.
- **Сгенерировано, а не переписано руками** (`dev/codegen/`) — методы, модели ответов, енумы и фасады рендерятся из официальной OpenAPI-спеки за гейтом ruff+mypy. `format: binary` автоматически становится типом `Media`.

## Кодогенерация

Две фазы: `generate` рендерит в staging и не трогает библиотеку, `install` продвигает staging в `src/pylzt/` за гейтом и откатывается при любой ошибке. Библиотека на диске никогда не остаётся сломанной после регена.

```bash
python -m dev.codegen build            # generate + install, обычный случай
python -m dev.codegen build --scrape   # сначала перескрейпить спеку
python -m dev.codegen generate         # только рендер в dev/codegen/generated/
python -m dev.codegen install          # только продвижение staging → библиотека
python -m dev.codegen scrape           # только скрейп + слияние спеки
python -m dev.codegen check            # только гейт ruff+mypy+import, без регена
```

| Флаг | Где | Что делает |
|---|---|---|
| `--api market\|forum\|antipublic` | `generate`, `build` | ограничить одним API (повторяемый); по умолчанию все три |
| `--scrape` | `generate`, `build` | перекачать readme.io-справочник перед рендером |
| `--refresh` | `*--scrape`, `scrape` | игнорировать дисковый кэш страниц |
| `--model-backend {pydantic,dataclass}` | `generate`, `build` | таргет для DTO ответов; по умолчанию `pydantic` |
| `--no-validate` | `install`, `build` | пропустить гейт (опасно, только для локального просмотра) |
| `--site market\|forum\|antipublic` | `scrape` | ограничить скрейп одним сайтом |

Слитые спеки `dev/generated/openapi/lzt_{market,forum,antipublic}.json` **закоммичены** — свежий клон собирается без скрейпа. Остальное под `dev/generated/` в gitignore.

Каждый сгенерированный файл несёт `Generated by forge — DO NOT EDIT`: спека не всегда совпадает с тем, что API реально отдаёт, и реген затрёт правку руками. Что проверено вживую, что сломано и как патчить расхождение спека/реальность — [`docs/codegen-runbook.md`](docs/codegen-runbook.md).

## Разработка

```bash
git clone https://github.com/open-lzt/pylzt && cd pylzt
uv sync --extra dev
git config core.hooksPath .githooks   # локальный гейт ruff+mypy+pytest на push
uv run pytest -q
```

E2E-тесты бьют по живому API, требуют `LZT_E2E_TOKEN` и исключены из прогона по умолчанию:

```bash
uv run pytest -m e2e -q
```

`.github/workflows/ci.yml` гоняет ruff, mypy и pytest на каждый push и PR. `.githooks/pre-push` — тот же гейт локально, чтобы красное ловилось до пуша, а не после.

Релизы едут по тегу `v*` — сборка, гейт и публикация на PyPI автоматические, порядок для мейнтейнера описан в [CONTRIBUTING.md](CONTRIBUTING.md).

## Экосистема

[lzt-testnet](https://github.com/open-lzt/lzt-testnet) — мок-маркет для тестов · [lzt-eventus](https://github.com/open-lzt/lzt-eventus) — движок событий · [auto-lzt](https://github.com/open-lzt/auto-lzt) — no-code автоматизации · [lzt-mcp](https://github.com/open-lzt/lzt-mcp) — сервер для AI-агентов · [весь стенд](https://github.com/open-lzt/open-lzt)

## Лицензия

[MIT](LICENSE)

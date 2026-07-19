<p align="right"><a href="README.en.md">English</a> · <b>Русский</b></p>

<div align="center">

# pylzt

<sub>Типизированный async-фреймворк над API lzt.market / lolzteam / AntiPublic — не тонкая HTTP-обёртка</sub>

[![CI](https://github.com/open-lzt/pylzt/actions/workflows/ci.yml/badge.svg)](https://github.com/open-lzt/pylzt/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/)
[![mypy: strict](https://img.shields.io/badge/mypy-strict-2a6db2)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/badge/lint-ruff-d7ff64)](https://docs.astral.sh/ruff/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

[Полная документация](docs/) · [Документация для AI-агентов](docs/for_ai/)

Типизированный async-**фреймворк** над API маркетплейса [lzt.market](https://lzt.market),
API форума [lolzteam](https://lolz.live) и API проверки утечек [AntiPublic](https://antipublic.one) —
не тонкая HTTP-обёртка.

**[Зачем фреймворк](#зачем-фреймворк-а-не-библиотека)** ·
**[Быстрый старт](#быстрый-старт)** ·
**[Sync](#sync-без-await)** ·
**[Мок](#против-мока-lzt-testnet)** ·
**[Пагинация](#пагинация)** ·
**[Батчинг](#батчинг-n-вызовов-в-один-запрос)** ·
**[Загрузка медиа](#загрузка-медиа)** ·
**[AntiPublic](#antipublic-api-проверки-утечек)** ·
**[Ошибки](#обработка-ошибок)** ·
**[Кодоген](#кодоген-билдер)**

## Зачем фреймворк, а не библиотека

Обёртка даёт типизированные методы поверх HTTP-клиента. pylzt поставляет саму
эксплуатационную машинерию, которая нужна продовой интеграции, — уже собранную и подключённую:

- **Пул токенов** (`token_pool/round_robin.py`) — round-robin по множеству токенов
  маркетплейса, каждый учитывается собственным бакетом на `RateClass` по официально
  опубликованным лимитам (Market 120/мин общий + 20/мин Category Search; Forum 300/мин).
  У AntiPublic свой пул с одним ключом (`token_pool/_static.py`) — лицензионный ключ
  не взаимозаменяем с OAuth-токеном, поэтому в общую ротацию он не попадает.
- **Пул прокси** (`proxy_pool/`) — sticky-per-token или round-robin egress-прокси
  (HTTP/HTTPS/SOCKS5) с отслеживанием здоровья через circuit-breaker на каждый прокси.
- **Отказоустойчивость** (`transport/base.py`, `lib/retry.py`) — повторы с джиттером
  backoff'а, уважающие `Retry-After`, типизированная само-регистрирующаяся иерархия
  ошибок (`errors.py`), схлопывающий запросы в один `/batch` (`lib/batch.py`), TTL-кэш,
  уважающий серверный `cacheTTL`.
- **Method-as-class** (`methods/base.py`) — каждый эндпоинт — это frozen Pydantic-модель
  `BaseMethod[T]`, а не вручную поддерживаемая функция: некорректные поля запроса
  падают на этапе конструирования, а не на проводе; `Client.execute(method)` — единственный
  путь выполнения запроса, к которому делегируют все доменные namespace'ы и все
  сгенерированные методы фасада.
- **Сгенерированный, а не переписанный вручную** (`dev/codegen/`) — методы, модели ответов,
  enum'ы и фасады генерируются из официального OpenAPI-референса и устанавливаются
  **плоско** в библиотеку за ruff+mypy-гейтом. Поля `format: binary` автоматически
  распознаются в реальный тип `Media`, поэтому эндпоинты загрузки файлов получают
  типизированную поддержку multipart бесплатно.
- **Sync и async на одном движке** (`sync/runner.py`) — `SyncClient` не является второй
  реализацией рейт-лимитинга и повторов; он запускает *тот же* async-движок в фоновом
  потоке с event loop'ом (`SyncRunner`), причём тип возврата каждого метода совпадает
  с развёрнутым типом его async-аналога под `mypy --strict`.

## Быстрый старт

```bash
pip install "git+https://github.com/open-lzt/pylzt.git"
```

```python
import asyncio

from pylzt import Client
from pylzt.types import Category


async def main() -> None:
    async with Client.from_token("<market-token>") as client:  # или Client.from_env() из $LZT_TOKEN
        lot = await client.market.get_lot(item_id=42)
        print(lot.item_id, lot.price, lot.title)

        async for lot in client.market.list_lots(category=Category.STEAM):
            print(lot.item_id, lot.price)


asyncio.run(main())
```

`client.market` / `client.forum` / `client.antipublic` — это три доменных namespace'а:
каждый эндпоинт из официальной спецификации — реальный метод на соответствующем
из них (`client.forum.threads_get(...)`, `client.antipublic.license_check_license()`).

## Sync без `await`

```python
from pylzt.sync.client import SyncClient

with SyncClient("<market-token>") as client:
    lot = client.market.get_lot(item_id=42)
```

## Против мока (lzt-testnet)

```python
from pylzt import Client, ClientConfig

async with Client.from_token("t", config=ClientConfig.for_testnet()) as client:
    ...  # всё бьётся в локальный мок 127.0.0.1:8765
```

## Пагинация

```python
from decimal import Decimal
from pylzt.types import Category, OrderBy

# стрим по страницам (max_pages — необязательный предел)
async for lot in client.market.list_lots(category=Category.STEAM, order_by=OrderBy.PRICE_ASC, max_pages=5):
    ...

all_lots = await client.market.list_lots(category=Category.STEAM, pmax=Decimal("500")).collect(limit=200)
first = await client.market.list_lots(category=Category.STEAM).first_page()
```

## Батчинг N вызовов в один запрос

Три способа — выбирай по тому, как вызовы возникают в твоём коде:

```python
from pylzt.methods.catalog import GetLot
from pylzt.methods.categories import CategoryParams
from pylzt.types import Category, ItemId

# 1. Список уже собран заранее — один POST /batch, один вызов.
results = await client.execute_batch([
    GetLot(item_id=ItemId(1)),
    CategoryParams(category=Category.STEAM),
])

# 2. Вызовы разбросаны по функции/циклу — оборачиваем регион, каждый execute()
#    внутри схлопывается в /batch-запросы вместо отправки по одному.
async with client.batching():
    lot, categories = await asyncio.gather(
        client.execute(GetLot(item_id=ItemId(1))),
        client.execute(CategoryParams(category=Category.STEAM)),
    )

# 3. Оборачивать нечего (например, вызовы возникают в несвязанных местах кода) — job()
#    схлопывается с любым другим одновременным вызовом job() через общий,
#    живущий весь клиент коллектор.
lot = await client.job(GetLot(item_id=ItemId(1)))
```

## Загрузка медиа

```python
from pylzt import Media

avatar = Media.from_path("avatar.png")
await client.forum.users_avatar_upload(user_id="me", avatar=avatar)
```

Про `media_storage=` (опциональный кэш байтов после загрузки) — см.
[`docs/integration-guide.md`](docs/integration-guide.md).

## AntiPublic (API проверки утечек)

Отдельный лицензионный ключ, не токен market/forum — он никогда не попадает в ту же
ротацию (см. обзор фреймворка выше):

```python
async with Client.from_token("<market-token>", antipublic_key="<antipublic-license-key>") as client:
    remaining = await client.antipublic.license_available_queries()
    hit = await client.antipublic.license_check_lines(lines=("user:pass",))
```

Вызов `client.antipublic.*` без `antipublic_key=` бросает `CredentialMissing` —
громкий отказ вместо тихого no-op.

## Обработка ошибок

Каждая ошибка, которую бросает SDK, — подкласс `LztError`: ловите конкретный тип,
из которого можете восстановиться, остальное пусть летит дальше:

```python
from pylzt import AuthFailed, NotFound, RateLimited, TransportError
from pylzt.types import ItemId

try:
    lot = await client.market.get_lot(item_id=ItemId(999_999_999))
except NotFound:
    ...  # лот не существует или не виден этому токену
except RateLimited as exc:
    ...  # exc несёт retry_after — пул токенов уже сам делает бэкофф
except AuthFailed:
    ...  # токен мёртв/отозван — выведите его из ротации, см. reconfigure()
except TransportError:
    ...  # 5xx апстрима после исчерпания повторов
```

Полный обзор — DI, конфиг, фейки для тестов, `reconfigure()` для живой ротации
токенов, полная таблица ошибок: **[`docs/integration-guide.md`](docs/integration-guide.md)**.

## Кодоген (билдер)

Методы SDK, модели ответов, enum'ы и фасады генерируются из официального
OpenAPI-референса на readme.io и устанавливаются **плоско** в библиотеку за
ruff + mypy-гейтом. `dev/codegen/` (`pipeline.py` + `generator.py` + `scraper.py`,
запускается через `python -m dev.codegen`) двухфазный: `generate` рендерит во
временное дерево и никогда не трогает библиотеку; `install` продвигает staging
в `src/pylzt/` за гейтом и откатывается при любом сбое — библиотека на диске
никогда не остаётся сломанной регеном.

### Команды

```bash
python -m dev.codegen generate                 # рендер только в dev/codegen/generated/
python -m dev.codegen install                  # продвинуть staging -> библиотеку, за гейтом
python -m dev.codegen build                     # generate + install за один проход (частый случай)
python -m dev.codegen build --scrape            # сначала пере-скрейпить OpenAPI-спеку, потом build
python -m dev.codegen scrape                    # только скрейп + слияние спеки, без кодогена
python -m dev.codegen check                     # запустить ruff + mypy + import-гейт, без регена
```

Полезные флаги (повторяемые, свободно комбинируются):

| Флаг | На каких командах | Эффект |
|---|---|---|
| `--api market` / `--api forum` / `--api antipublic` | `generate`, `build` | ограничить одним API (повторяемо); по умолчанию — все три |
| `--scrape` | `generate`, `build` | пере-скачать референс readme.io перед рендером |
| `--refresh` | `generate --scrape`, `build --scrape`, `scrape` | игнорировать дисковый кэш страниц, перекачать каждую страницу |
| `--model-backend {pydantic,dataclass}` | `generate`, `build` | цель для response-DTO; по умолчанию `pydantic` (методы запросов всегда frozen Pydantic-модели) |
| `--no-validate` | `install`, `build` | пропустить ruff+mypy-гейт при установке (опасно — только для быстрого локального взгляда на staged-вывод) |
| `--site market` / `--site forum` / `--site antipublic` | `scrape` | ограничить скрейпинг одним сайтом (повторяемо) |

### Что делает каждая фаза

- **`scraper.py`** скачивает каждую referen-страницу readme.io для сайта и объединяет
  вложенные фрагменты OpenAPI 3.1 в одну слитую спеку, кэшируя каждую страницу на диске
  под `dev/generated/openapi/.page_cache/<site>/` (`--refresh` обходит кэш). Слитая спека
  пишется в `dev/generated/openapi/lzt_<site>.json` — **эти JSON-файлы версионируются**
  (см. ниже); кэш страниц и логи скрейпа рядом с ними — нет.
- **`generator.py`** превращает эту спеку в типизированные method-классы (`BaseMethod[T]`),
  вложенные Pydantic-модели ответов, `StrEnum`, async-методы фасада и параллельный
  **sync**-фасад на каждый сайт (`facades/sync_{api}.py` — каждый метод — тонкая блокирующая
  обёртка над своим async-аналогом через `SyncRunner`, без второй реализации,
  выведенной из спеки) — плоско в `dev/codegen/generated/{methods,models,enums,facades}/`.
  Также прогоняет проход нормализации над сырой экстракцией, чтобы вывод оставался
  качества "написан вручную", а не буквальным дампом 1:1 из спеки — сворачивая
  структурно-идентичные модели в один класс, поднимая общие generic-базы, отображая
  поля запроса `format: binary` в реальный тип `Media`, и **переиспользуя написанные
  вручную примитивы вместо их дублирования**: любой enum, у которого значения на
  проводе — `{yes, no, nomatter}` (или подмножество), схлопывается на единственный
  `pylzt.types.Tristate` — с classmethod'ом `Tristate.from_bool(value: bool | None)` —
  вместо дублирующего класса той же формы на каждое имя поля (`Tel`, `EditBtag`,
  `ClashPass`, ...); любая модель ответа, у которой ведущее поле — `status: str`,
  переезжает на `pylzt.models.base.BaseResponse`, которому принадлежит `is_ok()`,
  вместо того чтобы каждая модель носила свою копию этого поля. `EXISTING_TYPES_ENUMS`
  в `generator.py` — полный список написанных вручную enum'ов, которые кодоген
  импортирует, а не регенерирует.
- **`pipeline.py`** снимает снапшот текущих установленных сгенерированных файлов,
  стирает их (чтобы файл удалённого домена исчезал на следующем build'е), копирует
  staged-набор внутрь, запускает `ruff --fix`, затем ruff+mypy+import-гейт, и
  восстанавливает снапшот при любом сбое.

Сгенерированные и написанные вручную модули сосуществуют плоско в одном пакете —
сгенерированные несут маркер авто-заголовка и имя с префиксом `{api}_` / `{api}`,
написанные вручную — без префикса, и `install` отказывается перезаписывать
написанный вручную модуль (`_guard_no_clobber`). Полный контракт — в
`dev/codegen/_MODULE.md`.

### Схема API

`dev/generated/openapi/lzt_market.json`, `lzt_forum.json` и `lzt_antipublic.json` —
слитые OpenAPI-спеки, которые производит `scraper.py`, — закоммичены, чтобы клон
мог выполнить `python -m dev.codegen build` без пере-скрейпа readme.io. Всё остальное
под `dev/generated/` (кэш страниц, логи скрейпа и staging-дерево
`dev/codegen/generated/`) остаётся в gitignore и пересобирается по требованию.
Пере-скрейпить с `python -m dev.codegen scrape --refresh`, когда апстрим-референс
меняется, и закоммитить обновлённые JSON-файлы вместе с диффом кодогена, который они
производят.

### Живая верификация

Каждый сгенерированный файл несёт докстринг `Generated by forge — DO NOT EDIT` —
заявленные в спеке типы не всегда совпадают с тем, что реально возвращает API, поэтому
свежий реген — никогда не место для ручного патча. `tests/pylzt/e2e/test_live_read.py`
(маркер `e2e`, нужен `LZT_E2E_TOKEN`, исключён из запуска по умолчанию) автоматически
находит и прогоняет каждый GET-эндпоинт без аргументов против реального API. Что уже
проверено, что всё ещё известно как сломанное, и механизм ручного патча для починки
расхождения спеки и реальности без того, чтобы следующий прогон кодогена тихо его
откатил — см. **`docs/codegen-runbook.md`**.

## Разработка

GitHub Actions недоступен на этом аккаунте (заблокирован до подключения способа
оплаты), поэтому `.github/workflows/ci.yml` сегодня не является рабочим гейтом.
`.githooks/pre-push` зеркалит его локально (ruff check, ruff format --check, mypy,
pytest) и блокирует push при сбое. После клонирования один раз укажите git на него:
`git config core.hooksPath .githooks`.

## Контрибьютинг

```bash
git clone https://github.com/open-lzt/pylzt && cd pylzt
uv sync --extra dev
git config core.hooksPath .githooks   # локальный ruff+mypy+pytest-гейт на push, см. выше
uv run pytest -q
```

PR идут против `main`. `.githooks/pre-push` — актуальный гейт прямо сейчас (см.
"Разработка" выше) — он должен пройти до того, как push пройдёт.

## Авторы

- [zlexdev](https://github.com/zlexdev)

## Лицензия

[MIT](LICENSE).

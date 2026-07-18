# framework-v2 — overview

Консолидированный план по итогам ревью сессии + живого API-прогона + разбора
codegen-раннбука (2026-07-07). Пять независимых треков, у каждого свой
worktree/`feat/<slug>`, реализуются по одному, не параллельно (треки 2 и 4
затрагивают общие файлы — `client.py`, `transport/`).

## Трек 1 — `storage/` пакет вместо `lib/storage.py` + `lib/cursor_storage.py`

**Цель**: `lib/storage.py` (`BaseStorage`/`BatchJobRecord`/`MemoryStorage`) и
`lib/cursor_storage.py` (`BaseCursorStorage`/`ExportCursor`/`MemoryCursorStorage`)
— оба persistence-seam для «истории записей» (job history / export cursor) —
переезжают в `storage/{base.py→batch.py, cursor.py}`, по образцу layout
`token_pool/`/`proxy_pool/` (`base.py` + сиблинги, `__init__.py` ре-экспорт).

**Не трогаем**: `lib/cache.py` (`BaseCache`), `lib/media_storage.py`
(`BaseMediaStorage`) — другой концерн (кэш/медиа, не job-history), остаются в `lib/`.

**Touch** (3 импортирующих файла, `verified-by-code`):
- `client.py:40` — `from pylzt.lib.storage import BaseStorage, BatchJobRecord, MemoryStorage`
- `lib/batch.py:40` — тот же импорт
- `export/resumable_exporter.py:8` — `from pylzt.lib.cursor_storage import BaseCursorStorage, ExportCursor`

**Approach**:
1. `git mv lib/storage.py storage/batch.py`, `git mv lib/cursor_storage.py storage/cursor.py`.
2. `storage/__init__.py` — ре-экспорт `BaseStorage, BatchJobRecord, MemoryStorage,
   BaseCursorStorage, ExportCursor, MemoryCursorStorage` (публичный фасад пакета).
3. Обновить 3 импорта на `from pylzt.storage import ...` (плоско через
   `__init__.py`, не `storage.batch`/`storage.cursor` — единая точка входа).
4. `docskill` regen для `lib/` и нового `storage/`.

**Risk**: нет — чисто механическое перемещение, тестов на сами модули нет (по
разведке), покрытие идёт через `client.py`/`lib/batch.py` тесты — они не меняются.

**Test**: полный `pytest` зелёный (существующая сюита ловит любой сломанный импорт).

## Трек 2 — `models/` полностью на Pydantic

**Разведка (инвентарь `@dataclass` вне `models/`, 17 штук)**:

| Файл | Класс | frozen/slots | Годится под Pydantic? |
|---|---|---|---|
| `config.py` | `ClientConfig` | frozen, slots | да — validation-at-construction для конфига реально полезна |
| `lib/batch.py` | `BatchJobResult` | frozen, slots | да |
| `lib/cursor_storage.py`/`storage/cursor.py` | `ExportCursor` | frozen, slots | да |
| `lib/storage.py`/`storage/batch.py` | `BatchJobRecord` | frozen, slots | да |
| `media.py` | `Media` | frozen, slots | да |
| `pagination.py` | `Page[T]` | frozen, slots | да (generic — Pydantic generics ОК) |
| `proxy_pool/base.py` | `ProxyAuth`, `Proxy` | frozen, slots | да |
| `proxy_pool/health.py` | `ProxyHealth` | slots (mutable) | да — `BaseModel` без `frozen`, `validate_assignment=False` (см. решение ниже) |
| `token_pool/base.py` | `Token`, `Lease` | frozen, slots | да |
| `token_pool/bucket.py` | `TokenBucket`, `RateBucketSet` | slots (mutable) | да — `BaseModel` без `frozen`, `validate_assignment=False` (см. решение ниже) |
| `token_pool/rate_limit.py` | `RateLimitSnapshot` | frozen, slots | да |
| `transport/base.py` | `ProxySpec`, `Request`, `Response` | frozen, slots | да — `BaseModel(frozen=True)`, overhead на горячий путь принят явно (см. решение ниже) |

**Решение (подтверждено пользователем — конвертировать ВСЕ 17, без исключений)**:
изначальная рекомендация — оставить `TokenBucket`/`RateBucketSet`/`ProxyHealth`
(горячий мутируемый счётчик) и `Request`/`Response` (строятся на каждый HTTP-вызов)
на dataclass — **отклонена**. Пользователь: «я думал ваще все датаклассы» — значит
весь пакет вне `models/` переезжает на Pydantic, включая горячие мутируемые типы.
Performance-компромисс фиксируется явно (не гадать, мерить):

- **Мутируемые** (`TokenBucket`, `RateBucketSet`, `ProxyHealth`) — конвертируются
  в `BaseModel` **без** `frozen=True` (мутация должна остаться возможной,
  `try_consume()`/health-update пишут поля напрямую). `model_config =
  ConfigDict(validate_assignment=False)` — валидация на **создание** объекта
  остаётся (ловит опечатки в конструкторе), но не на каждое присвоение поля в
  горячем пути (`validate_assignment=True` пересчитывало бы валидацию на каждый
  `try_consume()` — здесь это неоправданный tax, отключаем сознательно).
- **`Request`/`Response`** (`transport/base.py`) — конвертируются в
  `BaseModel(frozen=True)` как и остальные immutable-типы. Overhead на каждый
  HTTP-вызов принимается — единообразие важнее локальной оптимизации горячего
  пути (явный трейд-офф, зафиксирован пользователем, не деградация по недосмотру).
- **Замер после конвертации** — трек 2 не завершён без быстрого бенчмарка
  (`pytest-benchmark` или ручной `timeit` на `try_consume`/`Request` construction,
  до/после) в отчёте о завершении трека — если overhead неприемлемый, это
  всплывёт здесь, а не тихо в проде.

Все 17 dataclass — конвертировать в `BaseModel` (`frozen=True` для immutable,
без `frozen` для мутируемых счётчиков выше) — ловит опечатки в конструкторах на
этапе создания, а не в рантайме на первом использовании поля, единообразно с
`models/`.

**Approach**:
1. По одному файлу — `@dataclass(frozen=True, slots=True)` → `class X(BaseModel):
   model_config = ConfigDict(frozen=True)` (immutable) либо `class X(BaseModel):
   model_config = ConfigDict(validate_assignment=False)` (мутируемые счётчики,
   без `frozen`). `slots=True` у dataclass не имеет прямого Pydantic-эквивалента
   1:1 — Pydantic v2 модели уже компактны (`__slots__`-подобное поведение через
   `model_fields`), отдельно включать не нужно.
2. Замена конструкторов на call sites, где был позиционный вызов
   (`Token(TokenId(...), "cred")`) — Pydantic v2 по умолчанию требует kwargs
   для полей без `Field(...)` позиционных алиасов; грепнуть все call sites
   перед началом (десятки, не сотни — внутренние типы, не domain-модели).
3. Тесты, где идёт `dataclasses.is_dataclass(x)`/`dataclasses.replace(x, ...)` —
   найти и поменять на `isinstance(x, BaseModel)`/`x.model_copy(update=...)`
   (прецедент: `test_methods_declarative.py` уже прошёл ровно эту миграцию
   для `BaseMethod`, см. `docs/codegen-runbook.md` "Separate, pre-existing bug…").
4. Прямая мутация полей (`bucket.tokens -= n`) на мутируемых `BaseModel` работает
   как и на dataclass (без `frozen`, Pydantic v2 позволяет `obj.field = x`) —
   но если найдутся call sites через `dataclasses.replace()` на *мутируемых*
   типах — заменить на прямое присвоение, не `model_copy` (не создавать копию
   в горячем пути ради иммутабельного стиля, которого тут больше нет).

**Test**: полный `pytest` + `mypy --strict` — Pydantic-модели типизируются иначе
(`model_config`, `Field`), mypy plugin для pydantic уже должен быть в конфиге
(проверить `pyproject.toml` `[tool.mypy]` на `plugins = ["pydantic.mypy"]`
перед стартом — если нет, добавить, иначе типы полей не проверятся строго).

## Трек 3 — Live-схема: типизация `items`/`stickyItems` + чистка `UNVERIFIED` + full e2e (все reads)

### 3a. `CartGetResponse.items`/`stickyItems` — раздельные модели, не `dict[str, Any]`

Пользователь: «не ослабляй, а типизируй; если типы совсем разные — делай разные
модели». `CartGetResponse` сейчас шарится 4 эндпоинтами (`CartGet`/
`ListFavorites`/`ListOrders`/`CategoryAll`) с **разными** формами `items` —
единый generic тут не натягивается (это и есть причина исходного лузинга до
`dict[str, Any]`, задокументированная в файле).

**Approach**:
1. Живой захват (`LZT_E2E_TOKEN`, см. 3c) по каждому из 4 эндпоинтов отдельно —
   `exc.errors(include_input=True)` или прямой dump `response.body`, не гадать
   форму по памяти (жёсткое правило проекта, см. `docs/codegen-runbook.md`).
2. Если формы совпадают между эндпоинтами → один переиспользуемый item-класс.
   Если различаются → 4 раздельных Response-класса
   (`CartGetResponse`/`ListFavoritesResponse`/`ListOrdersResponse`/
   `CategoryAllResponse`), каждый со своим `items: list[<SpecificItem>]`, вместо
   одного класса на 4 эндпоинта с общим полем неясной формы.
3. `stickyItems` — из вставленной пользователем readme.io-схемы это полноформатный
   lot-like объект (`item_id`/`item_state`/`category_id`/`title`/`price`/
   `bumpSettings`/…) — почти наверняка тот же класс, что и market lot/category
   item; сверить с существующими `models/market/*_item.py` на предмет 1:1
   переиспользования, не плодить пятый дубликат схожей схемы.
4. Обновить `docs/codegen-runbook.md` новой записью (дата, что показал live-захват).

**Risk**: `_guard_no_clobber` уже не даст следующему `dev.codegen build --api
market` тихо затереть это — файл остаётся hand-patched, ловушка сохраняется.

### 3b. Убрать шаблонный `UNVERIFIED` маркер (262 файла) — НЕ трогать 5 содержательных

Инвентарь (`verified-by-code`, скрипт-грep по `src/pylzt/**/*.py`):
- **262 файла** несут идентичный шаблонный докстринг
  `"""UNVERIFIED — from the official OpenAPI spec. Confirm live before shipping."""`
  (`enums/market.py` ×42, `enums/forum.py` ×15, плюс ~205 model-файлов по 1).
  Текущий `dev/codegen/generator.py` **уже не генерирует** эту строку
  (`render_enum()` строка 1503-1509 сейчас пишет `"""Generated by forge — DO NOT
  EDIT. From the official OpenAPI spec."""`) — установленные файлы просто
  устарели относительно шаблона. Вторая часть пользовательского запроса
  («в билдере пусть тоже не ставится») уже выполнена, менять генератор не нужно.
- **5 файлов** несут содержательные, специфичные `UNVERIFIED`-пометки
  (`methods/balances.py`, `methods/categories.py`, `models/category.py` ×3) —
  это ручные комментарии по правилу проекта («помечай неуверенные технические
  утверждения»), не шаблон билдера. **Не трогать** — несут реальную информацию
  (например «no HAR capture yet — never invent a third-party shape»).

**Approach**: обычный `dev.codegen build` заблокируется на 48 hand-patched
файлах (см. 3d) — механическая regenerate-стратегия не работает как есть.
Вместо неё: скриптовый point-fix — убрать ровно эту докстринг-строку (оба
варианта: однострочный и многострочный) из всех файлов, где она есть И файл
**не** hand-patched (проверка по заголовку — `_is_generated()`-эквивалент),
т.е. из ~214 файлов (262 минус 48 hand-patched, минус проверка пересечения
— часть hand-patched файлов тоже могла нести этот маркер до патча, но раз они
уже переписаны с новым докстрингом, пересечение скорее всего пустое, сверить
по факту). Прогнать ruff+mypy+pytest после.

### 3c. Полный e2e read-прогон — ВСЕ read-запросы, не подмножество

Прошлый прогон (`pytest -m e2e`) не включал AntiPublic (`CredentialMissing` на
всех 5 antipublic-эндпоинтах — фикстура `client` в `test_live_read.py:96` не
передаёт `antipublic_key`). «Все read» = market + forum + antipublic.

**Подтверждено**: `LZT_E2E_ANTIPUBLIC_KEY` **нет** (отдельная лицензия не
приобретена/не выдана) — antipublic-тесты остаются в skip на неопределённый
срок, это не блокер трека, просто пробел в покрытии, задокументированный явно.

**Approach**:
1. Фикстура `client()` в `test_live_read.py` — добавить `antipublic_key`
   параметр (env var `LZT_E2E_ANTIPUBLIC_KEY`, отдельно от `LZT_E2E_TOKEN` —
   разные учётки/лицензии, см. `token_pool/_static.py`), skip antipublic-тестов
   персонально если ключ не задан (не весь модуль) — **ключа сейчас нет, значит
   эти 5 тестов остаются в skip после этого трека**, это ожидаемо, не баг.
2. Прогнать `pytest -m e2e -v` целиком с `LZT_E2E_TOKEN` (market+forum) —
   antipublic пропускается по п.1.
3. Каждый новый `ValidationError`/неожиданный fail (не входящий в
   `_EXPECTED_GAPS`) — живой capture → hand-patch по той же дисциплине, что и
   раннбук, с записью в `docs/codegen-runbook.md`.
4. Если/когда ключ появится — прогнать antipublic отдельно вне этого трека
   (не блокировать план на отсутствующем секрете).

### 3d. `_guard_no_clobber` — per-файл skip вместо all-or-nothing abort

Отвечает на прямой вопрос пользователя про «исключения»: механизм уже есть
(маркер в заголовке файла), но гранулярность неверная — один коллидирующий
файл валит всю установку (~90 методов + ~700 моделей market+forum одним
блоком). 48 hand-patched файлов сейчас застревают в этом.

**Approach** (`dev/codegen/pipeline.py::_guard_no_clobber`):
- Вместо `raise CodegenError(...)` на непустой `clashes` — по каждому клэшу
  `print`/`log.warning` («skipped N hand-patched files: …, see codegen-runbook.md»)
  и **исключить** эти файлы из `staged` перед копированием, установка
  продолжается для остального. Жёсткий `raise` оставить только для не по правилам
  собранного clash-списка (например, если один и тот же файл коллидирует, но
  никогда не был hand-patched намеренно — тут разницы для скрипта нет, полагаемся
  на маркер как единственный источник истины, как и раньше).
- Добавить `pipeline.install()` в отчёт: сколько файлов реально установлено,
  сколько пропущено (видимость вместо тихого прохода).

**Test**: юнит-тест на `_guard_no_clobber` — clash с hand-patched файлом не
поднимает исключение, файл исключён из установленного набора, остальные файлы
устанавливаются.

## Трек 4 — Убрать `RateLimitedTransport`, слить rate-limit/retry/governor в базовый транспорт

**Текущая архитектура** (`verified-by-code:src/pylzt/transport/rate_limited.py`):
`RateLimitedTransport(BaseTransport)` оборачивает сырой `BaseTransport`
(`HttpxSession`) и композирует `BaseTokenPool` (lease/rate-limit) +
`BaseRetryPolicy` (retry) + `BaseConcurrencyGovernor` (AIMD-гейт, добавлено
этой сессией) — итого ДВА вложенных `BaseTransport` на каждый вызов
(`HttpxSession` внутри `RateLimitedTransport`).

**Целевая архитектура**: rate-limit/retry/governor — не отдельный
оборачивающий `BaseTransport`, а **опциональные** зависимости самого
`HttpxSession` (или общего базового класса `BaseTransport`, если логика
lease/sign/retry должна быть переиспользуема без HTTP-специфики — решить на
месте). Если `token_pool`/`retry`/`concurrency_governor` не переданы —
транспорт работает как голый HTTP-клиент, `send()` просто отправляет запрос
без lease/retry/gate. Один `BaseTransport` вместо двух вложенных.

**Design decision — подтверждено пользователем: (B).** Куда физически переезжает
lease→sign→retry→report-логика —

- **(A) В `HttpxSession` напрямую** — `HttpxSession.__init__(*, token_pool=None,
  retry=None, concurrency_governor=None, ...)`, `send()` условно оборачивает
  себя в lease/retry при наличии зависимостей. Минус: `HttpxSession` перестаёт
  быть «чистым HTTP-клиентом» (нарушает текущий Single Responsibility из
  `transport/session.py`'s docstring), любая будущая альтернативная реализация
  транспорта (не httpx) дублирует всю lease/retry-логику заново.
- **(B) `BaseTransport` — абстрактный класс с шаблонным методом** — `send()`
  в базовом классе делает lease/retry/gate (если зависимости заданы), вызывает
  abstract `_send_raw(req)` для фактической отправки; `HttpxSession` реализует
  только `_send_raw`. Минус: `BaseTransport` перестаёт быть чистым интерфейсом
  (`BaseTransport.send` больше не abstract у всех implementers — но
  `_StaticBearerPool`-style consumers типа `BatchExecutor`/тестовые
  fake-транспорты, которые сегодня реализуют `BaseTransport.send()` напрямую,
  ничего не потеряют — они просто не проходят через lease-логику, что и
  соответствует «если лимитер не передан — не работает»).
- **(C) Composition остаётся, но `RateLimitedTransport` переименовывается и
  документируется как «декоратор», не «второй транспорт»** — минимальное
  изменение (по сути отказ от требования «убрать»), не то, что просили.

Выбрано **(B)** — сохраняет чистое разделение (транспорт = HTTP-io,
шаблонный метод = политика), не плодит HTTP-специфичный god-class, и
существующие fake-транспорты в тестах (`MemoryTransport`, `_StubTransport`
и т.д., реализующие `BaseTransport.send()` напрямую) продолжают работать без
lease/retry/gate ровно как и раньше — это и есть «если лимитер не передан, то
не работает».

**Touch** (не полный список, требует ре-аудита при старте трека):
- `transport/base.py` — `BaseTransport` получает `__init__(*, token_pool=None,
  retry=None, concurrency_governor=None, metrics=None, clock=None,
  enable_server_rate_sync=True)`, `send()` — шаблонный метод, `_send_raw()` —
  новый abstract.
- `transport/session.py` — `HttpxSession._send_raw()` вместо `send()`.
- `transport/rate_limited.py` — **удалить файл**, логика `send()`/
  `_report_outcome()` переезжает в `BaseTransport`.
- `client.py::_rate_limited()` — упраздняется, `_raw_transport()` сразу
  конструирует `HttpxSession(..., token_pool=pool, retry=self._retry, ...)`.
- Все тесты, импортирующие `RateLimitedTransport` напрямую
  (`test_client_loop.py`, `test_rate_limited_governor.py`,
  `test_client_batching.py` и др. — грепнуть перед стартом) — конструктор
  меняется с `RateLimitedTransport(transport, pool, ...)` на
  `HttpxSession(..., token_pool=pool, ...)` либо на fake-транспорт с теми же
  kwargs, если тест уже использует fake.

**Risk**: это самый рискованный трек сессии — трогает горячий путь каждого
запроса, пересекается с Треками 2 (если `Request`/`Response` останутся
dataclass — ок, не блокирует) и требует полного ре-прогона e2e (Трек 3c) после
слияния, чтобы подтвердить lease/retry/rate-sync/governor не сломались.

## Порядок исполнения

1. **Трек 1** (storage/) — изолированный, дешёвый, разблокирует чистую
   структуру для остального. `~150 LOC`.
2. **Трек 3b+3d** (UNVERIFIED cleanup + guard fix) — независим от остального,
   чисто codegen-инфраструктура. `~100 LOC` + скрипт на разовый прогон.
3. **Трек 3a+3c** (типизация items/stickyItems + полный e2e) — требует живого
   токена (market+forum+antipublic), человеческий gate на review каждого
   hand-patch. Размер непредсказуем до живого захвата.
4. **Трек 2** (full pydantic) — после треков 1/3, чтобы не мержить с
   параллельно двигающимися storage/model файлами. `~400-600 LOC` по инвентарю.
5. **Трек 4** (убрать RateLimitedTransport) — последний, самый рискованный,
   трогает то, что уже стабилизировано треками 1-2. Требует явного решения по
   дизайн-развилке (A/B/C выше) **до старта** — эскалирую в чат.

Каждый трек — свой `git worktree add ../aiolzt-<slug> -b feat/<slug> main`,
свой прогон ruff+mypy+pytest до мержа, порядок последовательный (не
параллельный — треки 2 и 4 оба трогают `client.py`/`transport/`).

## Решения по открытым вопросам (закрыты пользователем)

1. **Трек 4, развилка A/B/C** → **(B)** — шаблонный метод в `BaseTransport`,
   `_send_raw()` abstract у `HttpxSession`.
2. **Трек 3c** → `LZT_E2E_ANTIPUBLIC_KEY` **нет** — antipublic-тесты остаются
   в skip, не блокер, покрытие ограничено market+forum до появления ключа.
3. **Трек 2** → **все 17 dataclass конвертируются в Pydantic**, включая горячие
   мутируемые счётчики (`TokenBucket`/`RateBucketSet`/`ProxyHealth` — `BaseModel`
   без `frozen`, `validate_assignment=False`) и `Request`/`Response`
   (`BaseModel(frozen=True)`, overhead на горячий путь принят явно). Единообразие
   важнее локальной оптимизации; бенчмарк до/после — обязательный пункт отчёта
   о завершении трека (не гадать про регрессию, измерить).

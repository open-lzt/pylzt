<p align="right"><a href="integration-guide.en.md">English</a> · <b>Русский</b></p>

# Руководство по интеграции

Полный обзор использования `pylzt` — типизированного async-SDK над API lzt.market /
lolz.live. Каждый сниппет ниже сверен с реальными сигнатурами в `src/pylzt/`; если
сигнатура меняется — обновляйте этот файл в том же PR.

## Установка

```bash
pip install "git+https://github.com/open-lzt/pylzt.git"
```

## Быстрый старт

`Client` — асинхронный контекстный менеджер: `aclose()` запускается при выходе и
освобождает нижележащие HTTP-сессии.

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

`Client(tokens=...)` — единственный обязательный аргумент конструктора; всё
остальное (`transport`, `token_pool`, `proxy_source`, `retry`, `metrics`, `clock`,
кэши, `config`) имеет рабочее значение по умолчанию и существует для подстановки
фейка в тестах или другой политики — см. [Внедрение зависимостей](#внедрение-зависимостей).

## Чтение лотов

`client.market.get_lot` получает один лот по id; `client.market.get_lots_batch`
получает много лотов через серверный эндпоинт `/batch` (автоматически чанкуется
по серверному лимиту на job — вызывающему коду не нужно думать о размере батча):

```python
from pylzt.types import ItemId

lot = await client.market.get_lot(item_id=ItemId(123456))

lots = await client.market.get_lots_batch([ItemId(1), ItemId(2), ItemId(3)])
# отсутствующие id тихо пропускаются; порядок ввода сохраняется
```

### Пагинация

`client.market.list_lots(filter, *, max_pages=None)` возвращает `Paginator[Lot]` —
ничего не запрашивается, пока вы его не итерируете. `max_pages=None` означает
«листать, пока сервер не сообщит, что результатов больше нет».

```python
from decimal import Decimal

from pylzt.models.lot import LotFilter
from pylzt.types import Category, OrderBy

filt = LotFilter(category=Category.STEAM, pmax=Decimal("500"), order_by=OrderBy.PRICE_ASC)

# потоково, элемент за элементом, через страницы
async for lot in client.market.list_lots(filt, max_pages=5):
    ...

# или сразу вытянуть всё в список (опционально с лимитом)
all_lots = await client.market.list_lots(filt).collect(limit=200)

# или только первая страница, для быстрого взгляда
first = await client.market.list_lots(filt).first_page()
```

### Категории

```python
categories = await client.market.list_categories()
schema = await client.market.category_params(Category.STEAM)  # кэшируется на `category_params_ttl`
games = await client.market.category_games(Category.STEAM)
```

## Сгенерированный фасад (~200 эндпоинтов)

`client.market`/`client.forum`/`client.antipublic` — доменные namespace'ы: каждый
эндпоинт из официальной OpenAPI-спеки — реальный `async def` на соответствующем
namespace'е, например `client.forum.forums_list()`,
`client.forum.threads_get(thread_id)`, `client.forum.categories_get(...)`,
`client.antipublic.license_check_license()`. Они генерируются командой
`python -m dev.codegen build` (см.
[`docs/codegen-runbook.md`](codegen-runbook.md)) — не редактируйте вручную файл
с авто-заголовком. У части моделей в докстринге всё ещё есть заметка о живой
верификации там, где заявленная в спеке форма не совпадает с реальным ответом
(см. `docs/codegen-runbook.md`) — всё остальное сверено с продовым трафиком.

Для вызова, который не покрывает сгенерированный фасад, спускайтесь напрямую на
слой method-as-class через `execute` (остаётся на `Client`, а не на namespace —
это сквозная точка входа, к которой делегирует каждый namespace):

```python
from pylzt.methods.catalog import GetLot
from pylzt.types import ItemId

lot = await client.execute(GetLot(item_id=ItemId(42)))
```

### Выполнение нескольких методов как одного запроса

Три точки входа, все прогоняются через одну и ту же механику `/batch` (чанкуется
по серверному лимиту на job, группируется по market/forum, так как `/batch`
специфичен для хоста) — выбирайте по тому, как вызовы возникают в вашем коде:

**`execute_batch`** — список уже собран заранее:

```python
from pylzt.methods.catalog import GetLot
from pylzt.methods.categories import CategoryParams
from pylzt.types import Category, ItemId

results = await client.execute_batch([
    GetLot(item_id=ItemId(1)),
    CategoryParams(category=Category.STEAM),
])
```

**`batching()`** — вызовы разбросаны по функции/циклу; оборачиваем регион вместо
того, чтобы сначала собирать список. Каждый `execute()` внутри блока
автоматически схлопывается (окно задаётся `batch_linger`, флаш при выходе
из блока):

```python
async with client.batching():
    lot, categories = await asyncio.gather(
        client.execute(GetLot(item_id=ItemId(1))),
        client.execute(CategoryParams(category=Category.STEAM)),
    )
```

**`job()`** — оборачивать нечего (например, вызовы возникают в несвязанных
местах кода, которые вы не контролируете). `job()` схлопывается с любым другим
одновременным вызовом `job()`, сделанным через тот же клиент, через общий,
лениво создаваемый, живущий весь клиент коллектор — `async with` не нужен:

```python
lot = await client.job(GetLot(item_id=ItemId(1)))
```

Вызов `job()`, сделанный изнутри активного блока `batching()`, использует
коллектор этого блока вместо своего собственного — эти два механизма
компонуются, а не удваивают батчинг.

## AntiPublic (API проверки утечек)

Отдельный лицензионный ключ, не токен market/forum — передавайте его как
`antipublic_key=`, он никогда не попадает в ротацию токенов market/forum:

```python
async with Client(["<market-token>"], antipublic_key="<antipublic-license-key>") as client:
    remaining = await client.antipublic.license_available_queries()
    hit = await client.antipublic.license_check_lines(lines=("user:pass",))
```

Вызов любого метода `client.antipublic.*` без `antipublic_key=` бросает
`CredentialMissing("antipublic_key")` — громкий отказ вместо тихого no-op.
`config.antipublic_per_min` (по умолчанию 60) и `config.antipublic_base_url`
управляют его собственным рейт-лимитом и хостом, независимо от market/forum.

## Обработка ошибок

Каждая ошибка, которую бросает SDK, — подкласс `LztError`: ловите конкретный
тип, из которого можете восстановиться, остальное пусть летит дальше:

```python
from pylzt import AuthFailed, NotFound, RateLimited, TransportError

try:
    lot = await client.market.get_lot(item_id=ItemId(999_999_999))
except NotFound:
    ...  # лот не существует или не виден этому токену
except RateLimited as exc:
    ...  # exc несёт retry_after — пул токенов уже сам делает бэкофф
except AuthFailed:
    ...  # токен мёртв/отозван — выведите его из ротации, см. reconfigure() ниже
except TransportError:
    ...  # 5xx апстрима после исчерпания повторов
```

| Исключение | Когда бросается |
|---|---|
| `AuthFailed` | токен отклонён (401) |
| `Forbidden` | у токена нет scope/права на этот эндпоинт (403) |
| `NotFound` | ресурс не существует или не виден этому токену (404) |
| `BadRequest` | некорректный запрос (400) |
| `RateLimited` | 429 — несёт `retry_after`; пул токенов уже сам повторяет запрос внутри, наружу это всплывает только когда повторы исчерпаны |
| `CaptchaRequired` / `ProxyChallenge` | анти-бот заслон апстрима; нужно ручное вмешательство или другой egress-IP |
| `TransportError` | 5xx после того, как политика повторов сдалась |
| `RetryableUpstream` | временный сбой апстрима, который политика повторов уже обрабатывает — видно только если вы отключили retry |
| `ModelNotBound` | вызвана привязанная к клиенту операция (например, `lot.refresh()`) на модели, которая была построена/распарсена отдельно и никогда не возвращалась через `Client.execute` |
| `MethodDeclarationError` | у подкласса `BaseMethod` отсутствует `__url__`/`__returning__` — бросается на этапе определения класса, не в рантайме |

## Внедрение зависимостей

Каждый аргумент конструктора `Client` — интерфейс `Base*` с реализацией по
умолчанию — подставляйте свою для тестов или другого бэкенда без изменения
внутренностей SDK.

### Несколько токенов (масштабирование рейт-лимита)

У каждого токена свой бакет на `RateClass` (`GENERAL` 120/мин, `SEARCH` 20/мин,
`FORUM` 300/мин — официально опубликованные лимиты). Передача N токенов даёт
N-кратную пропускную способность, round-robin:

```python
client = Client(["token-a", "token-b", "token-c"])
```

### Прокси

```python
from pylzt.proxy_pool.source import Proxy, ProxyId, ProxyScheme, StaticProxySource

proxies = StaticProxySource([
    Proxy(proxy_id=ProxyId("p1"), scheme=ProxyScheme.SOCKS5, host="1.2.3.4", port=1080),
])
client = Client(["token-a"], proxy_source=proxies)
```

Прокси sticky per-token (один прокси остаётся привязан к токену, пока не
сработает его circuit breaker), а не round-robin на каждый запрос.

### Замена пула токенов/прокси на лету — без рестарта

`reconfigure()` горячо подменяет живой пул токенов; уже выданные leases
завершаются со старым пулом, следующий запрос подхватывает новый:

```python
client.reconfigure(token_pool=new_pool)
```

Это примитив, к которому стоит обращаться, если токены должны ротироваться
пока процесс продолжает работать (например, при перечитывании из secrets
store) — постройте небольшой цикл, который создаёт свежий `RoundRobinTokenPool`
и вызывает `reconfigure()` с интервалом; более тяжёлая абстракция не нужна,
если у вас нет конкретного требования, которое `reconfigure()` не покрывает.

### Фейки для тестов

`Clock`/`FakeClock`, `BaseMetrics`/`NullMetrics`, `BaseCache`/`MemoryCache`,
`BaseTransport` — все подменяемы одинаково — рабочие примеры фейков см. в
`tests/pylzt/test_client_request.py` и `tests/pylzt/test_client_loop.py`.

## Загрузка медиа

Эндпоинты с реальным файловым полем (сейчас это 4 метода загрузки/кропа
аватара/фона) принимают экземпляр `Media` вместо сырого пути или байтов:

```python
from pylzt import Media

avatar = Media.from_path("avatar.png")               # читает байты + определяет имя файла
# или: Media(data=raw_bytes, filename="avatar.png", content_type="image/png")

await client.forum.users_avatar_upload(user_id="me", avatar=avatar)
```

`Media.sha256` — хэш содержимого, удобен для дедупа/аудита на стороне
вызывающего — сама загрузка не дедуплицируется (контракт идемпотентности API
для повторной загрузки неизвестен, поэтому каждый вызов всё равно идёт в сеть).

Передайте `media_storage=` в `Client(...)`, чтобы кэшировать загруженные байты
после успешного вызова (по умолчанию `NullMediaStorage`, no-op — ничего не
кэшируется, пока вы не подключите это явно). `FileMediaStorage` — готовая
реализация на локальном диске: один файл сырых байтов на sha256-ключ плюс
`.json`-сайдкар для `filename`/`content_type` (одни байты не позволяют
восстановить их обратно), блокирующий I/O выполняется через
`asyncio.to_thread`, чтобы не подвешивать event loop:

```python
from pylzt import FileMediaStorage

client = Client(["token-a"], media_storage=FileMediaStorage("./media-cache"))
```

Реализуйте `BaseMediaStorage` сами для S3/удалённого хранилища:

```python
from pylzt import BaseMediaStorage, Media

class S3MediaStorage(BaseMediaStorage):
    async def get(self, key: str) -> Media | None: ...
    async def save(self, key: str, media: Media) -> None: ...
```

`save()`, который бросает исключение, никогда не роняет саму загрузку — это
best-effort кэш, а не часть пути успеха/неудачи запроса.

## Конфигурация

`ClientConfig` (все поля опциональны, показаны со значениями по умолчанию):

```python
from pylzt import ClientConfig

config = ClientConfig(
    base_url="https://prod-api.lzt.market",
    general_per_min=120,
    search_per_min=20,
    forum_base_url="https://prod-api.lolz.live",
    forum_per_min=300,
    antipublic_base_url="https://antipublic.one/api/v2",
    antipublic_per_min=60,
    request_timeout=30.0,
    per_page=50,
    batch_size=50,
    batch_linger=0.05,
    category_params_ttl=3600.0,
    enable_server_rate_sync=True,      # доверять серверным заголовкам рейт-лимита больше, чем локальному учёту
    enable_plugin_discovery=True,      # авто-загрузка entry-point middleware/metrics-бэкендов, см. ниже
    enable_adaptive_concurrency=False, # опциональный AIMD-governor конкурентности, см. ниже
)
client = Client(["token-a"], config=config)
```

### Адаптивная конкурентность (AIMD-governor)

`enable_adaptive_concurrency=True` подменяет дефолтную no-op-политику
конкурентности на AIMD-governor (additive-increase/multiplicative-decrease —
тот же принцип, что и у TCP congestion control): он расширяет лимит
одновременных запросов на `RateClass`, пока сервер сообщает о запасе, и резко
режет его в момент возврата сигнала рейт-лимита — полезно, когда вы заранее
не знаете безопасный потолок конкурентности и хотите, чтобы фреймворк нашёл
его сам, а не подбирать `general_per_min`/`search_per_min` методом проб
и ошибок:

```python
client = Client(["token-a"], config=ClientConfig(enable_adaptive_concurrency=True))
```

### Обнаружение плагинов (entry points)

`enable_plugin_discovery=True` (по умолчанию) автоматически подгружает любую
реализацию `BaseMiddleware`/`BaseMetrics`, которую сторонний пакет
регистрирует под группами entry-point `pylzt.plugins.middleware` /
`pylzt.plugins.metrics` — без изменений кода в приложении, импортирующем
`pylzt`, как только такой пакет установлен. Установите `False` для полностью
явного монтирования (работает только то, что явно передано в `Client(...)`),
либо чтобы отладить неожиданный middleware, всплывающий в трейсе запроса.

## Сквозной (end-to-end) референс

`tests/pylzt/e2e/test_live_read.py` прогоняет read-only запросы против
реального API (опционально, переменная окружения `LZT_E2E_TOKEN`,
`pytest -m e2e`) и является самым актуальным рабочим примером цепочки вызовов
(`list_categories` → `category_params` → `list_lots` → `get_lot`;
`forums_list` → `forums_get` → `threads_list` → `threads_get`). Прочтите его
перед тем, как копировать паттерн из этого руководства в продовый код — он
сверяется с живым API на каждом прогоне, где задан токен, а это руководство —
нет.

## См. также

- [`docs/codegen-runbook.md`](codegen-runbook.md) — как строится сгенерированный
  фасад, что уже проверено вживую, и механизм ручного патча для расхождения
  спеки и реальности.
- `README.md` — обзор возможностей на один абзац + справочник команд кодогена.

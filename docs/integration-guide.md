<p align="right"><a href="integration-guide.en.md">English</a> · <b>Русский</b></p>

# Гайд по интеграции

Полный разбор работы с `pylzt` — типизированным async-SDK над API lzt.market / lolz.live. Каждый фрагмент кода сверен с реальными сигнатурами в `src/pylzt/`; изменилась сигнатура — правьте этот файл тем же PR.

## Установка

```bash
pip install pylzt
# неотрелиженный main:  pip install "git+https://github.com/open-lzt/pylzt.git"
```

## Быстрый старт

`Client` — асинхронный контекстный менеджер: на выходе вызывается `aclose()` и освобождает HTTP-сессии.

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

Обязательный аргумент конструктора один — `Client(tokens=...)`. У всего остального (`transport`, `token_pool`, `proxy_source`, `retry`, `metrics`, `clock`, кэши, `config`) есть рабочий дефолт, и существует оно, чтобы подставить фейк в тестах или поменять политику — см. [Внедрение зависимостей](#внедрение-зависимостей).

## Чтение лотов

`client.market.get_lot` берёт один лот по id, `client.market.get_lots_batch` — много, через серверный `/batch`. Порезка на куски по серверному потолку задач происходит сама, размер батча вызывающего не касается.

```python
from pylzt.types import ItemId

lot = await client.market.get_lot(item_id=ItemId(123456))

lots = await client.market.get_lots_batch([ItemId(1), ItemId(2), ItemId(3)])
# отсутствующие id молча пропускаются; порядок входа сохраняется
```

### Пагинация

`client.market.list_lots(filter, *, max_pages=None)` возвращает `Paginator[Lot]` — до итерации не запрашивается ничего. `max_pages=None` означает «листать, пока сервер не скажет, что результатов больше нет».

```python
from decimal import Decimal

from pylzt.models.lot import LotFilter
from pylzt.types import Category, OrderBy

filt = LotFilter(category=Category.STEAM, pmax=Decimal("500"), order_by=OrderBy.PRICE_ASC)

# поштучно, сквозь страницы
async for lot in client.market.list_lots(filt, max_pages=5):
    ...

# или всё в список, при желании с потолком
all_lots = await client.market.list_lots(filt).collect(limit=200)

# или только первая страница, чтобы быстро глянуть
first = await client.market.list_lots(filt).first_page()
```

### Категории

```python
categories = await client.market.list_categories()
schema = await client.market.category_params(Category.STEAM)  # кэшируется на category_params_ttl
games = await client.market.category_games(Category.STEAM)
```

## Сгенерированный фасад (~200 эндпоинтов)

`client.market` / `client.forum` / `client.antipublic` — доменные неймспейсы. Каждый эндпоинт официальной OpenAPI-спеки это настоящий `async def` на своём неймспейсе: `client.forum.forums_list()`, `client.forum.threads_get(thread_id)`, `client.forum.categories_get(...)`, `client.antipublic.license_check_license()`.

Всё это генерируется командой `python -m dev.codegen build` — **файл с заголовком авто-генерации руками не правят.** У горстки моделей в docstring висит пометка о живой проверке: там объявленная спекой форма расходится с реальным ответом. Остальное сверено с боевым трафиком.

Если нужного вызова в фасаде нет, спускайтесь на уровень «метод как класс» через `execute`. Он живёт на `Client`, а не на неймспейсе — это сквозная точка входа, к которой сводятся сами неймспейсы.

```python
from pylzt.methods.catalog import GetLot
from pylzt.types import ItemId

lot = await client.execute(GetLot(item_id=ItemId(42)))
```

### Несколько методов одним запросом

Три входа, все сводятся к одной механике `/batch` — резка по серверному потолку задач и группировка отдельно по маркету и форуму, потому что `/batch` привязан к хосту. Выбирайте по тому, как вызовы возникают в коде.

**`execute_batch`** — список известен заранее:

```python
from pylzt.methods.catalog import GetLot
from pylzt.methods.categories import CategoryParams
from pylzt.types import Category, ItemId

results = await client.execute_batch([
    GetLot(item_id=ItemId(1)),
    CategoryParams(category=Category.STEAM),
])
```

**`batching()`** — вызовы разбросаны по функции или циклу: оборачивайте участок вместо того, чтобы сначала собирать список. Каждый `execute()` внутри блока склеивается сам (окно задаёт `batch_linger`, сброс — на выходе из блока):

```python
async with client.batching():
    lot, categories = await asyncio.gather(
        client.execute(GetLot(item_id=ItemId(1))),
        client.execute(CategoryParams(category=Category.STEAM)),
    )
```

**`job()`** — оборачивать нечего: вызовы приходят из мест, которыми вы не управляете. `job()` склеивается со всеми другими параллельными `job()` того же клиента через общий сборщик, создаваемый лениво на время жизни клиента. `async with` не нужен:

```python
lot = await client.job(GetLot(item_id=ItemId(1)))
```

`job()`, вызванный внутри активного `batching()`, берёт сборщик этого блока, а не свой — они складываются, а не батчатся дважды.

## AntiPublic

Отдельный лицензионный ключ, не токен маркета или форума. Передаётся как `antipublic_key=` и в общую ротацию не попадает.

```python
async with Client(["<market-token>"], antipublic_key="<antipublic-license-key>") as client:
    remaining = await client.antipublic.license_available_queries()
    hit = await client.antipublic.license_check_lines(lines=("user:pass",))
```

Любой вызов `client.antipublic.*` без `antipublic_key=` поднимает `CredentialMissing("antipublic_key")` — падаем громко, а не молча ничего не делаем. Свой лимит и хост задают `config.antipublic_per_min` (по умолчанию 60) и `config.antipublic_base_url`, независимо от маркета и форума.

## Обработка ошибок

Всё, что поднимает SDK, — подклассы `LztError`. Ловите тот тип, от которого умеете восстанавливаться, остальное пусть летит выше.

```python
from pylzt import AuthFailed, NotFound, RateLimited, TransportError

try:
    lot = await client.market.get_lot(item_id=ItemId(999_999_999))
except NotFound:
    ...  # лота нет или он не виден этому токену
except RateLimited as exc:
    ...  # exc.retry_after — пул токенов уже отступил сам
except AuthFailed:
    ...  # токен мёртв или отозван — убрать из ротации, см. reconfigure() ниже
except TransportError:
    ...  # upstream 5xx, ретраи исчерпаны
```

| Исключение | Когда поднимается |
|---|---|
| `AuthFailed` | токен отвергнут (401) |
| `Forbidden` | у токена нет прав на этот эндпоинт (403) |
| `NotFound` | ресурса нет или он не виден этому токену (404) |
| `BadRequest` | кривой запрос (400) |
| `RateLimited` | 429, несёт `retry_after`; пул токенов ретраит сам, наружу вылезает только когда ретраи исчерпаны |
| `CaptchaRequired` / `ProxyChallenge` | анти-бот на той стороне; нужен ручной разбор или другой исходящий IP |
| `TransportError` | 5xx после того, как политика ретраев сдалась |
| `RetryableUpstream` | временный сбой, который политика ретраев уже разруливает — виден только если ретраи выключены |
| `ModelNotBound` | вызов клиент-зависимой операции (`lot.refresh()`) на модели, которую собрали или распарсили отдельно, а не получили через `Client.execute` |
| `MethodDeclarationError` | у подкласса `BaseMethod` нет `__url__` или `__returning__` — падает в момент объявления класса, а не в рантайме |

## Внедрение зависимостей

Каждый аргумент конструктора `Client` — интерфейс `Base*` с реализацией по умолчанию. Подставляйте свою для тестов или другого бэкенда, не трогая внутренности SDK.

### Несколько токенов

У каждого токена своё ведро на `RateClass` (`GENERAL` 120/мин, `SEARCH` 20/мин, `FORUM` 300/мин — официальные опубликованные потолки). N токенов дают N-кратную пропускную способность по round-robin:

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

Прокси липнет к токену: один прокси держится за токеном, пока не сработает его circuit breaker. Это не round-robin на каждый запрос.

### Подмена пула на ходу, без рестарта

`reconfigure()` меняет живой пул токенов: аренды в полёте доигрывают на старом пуле, следующий запрос берёт новый.

```python
client.reconfigure(token_pool=new_pool)
```

Это тот примитив, за которым идут, когда токены надо ротировать без остановки процесса — например, перечитывая их из хранилища секретов. Достаточно небольшого цикла, который строит свежий `RoundRobinTokenPool` и по интервалу зовёт `reconfigure()`. Более тяжёлая абстракция нужна только под конкретное требование, которое `reconfigure()` не закрывает.

### Фейки для тестов

`Clock`/`FakeClock`, `BaseMetrics`/`NullMetrics`, `BaseCache`/`MemoryCache`, `BaseTransport` подменяются так же. Рабочие фейки — в `tests/pylzt/test_client_request.py` и `tests/pylzt/test_client_loop.py`.

## Загрузка файлов

Эндпоинты с настоящим файловым полем (сейчас это 4 метода загрузки и обрезки аватара и фона) принимают `Media`, а не путь или сырые байты.

```python
from pylzt import Media

avatar = Media.from_path("avatar.png")               # читает байты и выводит имя файла
# или: Media(data=raw_bytes, filename="avatar.png", content_type="image/png")

await client.forum.users_avatar_upload(user_id="me", avatar=avatar)
```

`Media.sha256` — хеш содержимого, удобен для дедупа и аудита на вашей стороне. Сама загрузка не дедуплицируется: контракт идемпотентности повторной загрузки у API неизвестен, поэтому каждый вызов идёт в сеть.

`media_storage=` в `Client(...)` кэширует загруженные байты после успешного вызова. По умолчанию стоит `NullMediaStorage`, то есть заглушка: без явного включения не кэшируется ничего. `FileMediaStorage` — готовая реализация на локальном диске: один файл сырых байт на ключ sha256 плюс `.json`-спутник для `filename` и `content_type` (одни байты их не переживут), блокирующий ввод-вывод уезжает в `asyncio.to_thread` и не стопорит event loop.

```python
from pylzt import FileMediaStorage

client = Client(["token-a"], media_storage=FileMediaStorage("./media-cache"))
```

Для S3 или удалённого хостинга реализуйте `BaseMediaStorage` сами:

```python
from pylzt import BaseMediaStorage, Media

class S3MediaStorage(BaseMediaStorage):
    async def get(self, key: str) -> Media | None: ...
    async def save(self, key: str, media: Media) -> None: ...
```

Упавший `save()` не роняет саму загрузку — это кэш по мере возможности, а не часть пути успеха или отказа запроса.

## Конфигурация

`ClientConfig`, все поля необязательные, показаны со значениями по умолчанию:

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
    enable_server_rate_sync=True,      # верить заголовкам сервера о лимитах больше, чем локальному учёту
    enable_plugin_discovery=True,      # автозагрузка middleware и метрик из entry points, см. ниже
    enable_adaptive_concurrency=False, # AIMD-регулятор конкурентности по желанию, см. ниже
)
client = Client(["token-a"], config=config)
```

### Адаптивная конкурентность (AIMD)

`enable_adaptive_concurrency=True` меняет пустую политику конкурентности на AIMD-регулятор — аддитивный рост, мультипликативное падение, из того же семейства, что управление перегрузкой в TCP. Он расширяет лимит запросов в полёте по каждому `RateClass`, пока сервер показывает запас, и резко режет его при первом же сигнале о лимите.

Полезно, когда безопасный потолок конкурентности заранее неизвестен и хочется, чтобы он нашёлся сам, а не подбирался вручную через `general_per_min` и `search_per_min`.

```python
client = Client(["token-a"], config=ClientConfig(enable_adaptive_concurrency=True))
```

### Обнаружение плагинов

`enable_plugin_discovery=True` (по умолчанию) автоматически подхватывает любые реализации `BaseMiddleware` и `BaseMetrics`, которые сторонний пакет зарегистрировал в группах entry points `pylzt.plugins.middleware` и `pylzt.plugins.metrics`. Как только такой пакет установлен, менять код приложения, импортирующего `pylzt`, не нужно.

Ставьте `False`, если хотите полностью явную сборку — работает только то, что передано в `Client(...)` — или чтобы разобраться, откуда в трейсе запроса взялась неожиданная middleware.

## Сквозной пример

`tests/pylzt/e2e/test_live_read.py` гоняет запросы на чтение против живого API (по желанию, переменная `LZT_E2E_TOKEN`, `pytest -m e2e`) и остаётся самым свежим рабочим примером сцепки вызовов: `list_categories` → `category_params` → `list_lots` → `get_lot` и `forums_list` → `forums_get` → `threads_list` → `threads_get`.

Прочитайте его, прежде чем тащить приём отсюда в боевой код: он сверяется с живым API на каждом прогоне с токеном, а этот гайд — нет.

## Смотрите также

- `README.md` — обзор возможностей и справочник по командам кодогенерации.

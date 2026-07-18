# Эндпоинт-специфичные идеи составных утилит

Раунд 3 — не generic-инфраструктура фреймворка (см. `00-overview.md` /
`01-ideas-expanded.md`), а конкретные удобные методы, объединяющие 2+ сырых
вызова эндпоинтов в один, либо закрывающие пробел, который оставляет сырой
API (пагинация, bulk-варианты, поллинг), в рамках одного домена.

🔴 = money/purchase/payment-adjacent — нужны idempotency-ключи и явная
верификация состояния, а не однострочник в стиле ponytail.

## Домен market

**Публикация аккаунтов**
- `publish_and_verify()` — объединяет `publishing_add` + `publishing_check` для авто-верификации листинга за один вызов
- `list_own_items_summary()` — обёртка над `list_user` (self), возвращает счётчики по категориям/статусам
- `bulk_quick_sell()` — объединяет `publishing_fast_sell` по списку items с авто-форматированием

**Управление аккаунтами**
- `item_state_tracker()` — опрашивает `managing_bulk_get`, пока статус item не сменится с исходного
- `batch_bump_all()` — тянет items из `list_user`, фильтрует поднимаемые, применяет `managing_bump` к каждому
- `item_guardian()` — составной `managing_check_guarantee` + `managing_refuse_guarantee` с авто-решением
- `transfer_with_verification()` — объединяет `managing_transfer` + `list_states` для подтверждения состояния после трансфера

**Покупка** 🔴
- `buy_and_confirm()` — объединяет `purchasing_check` → `purchasing_confirm`, обрабатывает round-trip кода подтверждения
- `fast_purchase_with_retry()` — оборачивает `purchasing_fast_buy` экспоненциальным backoff на транзиентных ошибках
- `batch_review_discounts()` — `cart_get` + фильтр по скидке + цепочка `purchasing_discount_review` на каждый item

**Платежи** 🔴
- `invoice_poller()` — опрашивает `payments_invoice_get`, пока статус не станет отличным от pending, с таймаутом
- `payout_estimate()` — объединяет `payments_fee` + `payments_payout_services`, показывает сумму после комиссии
- `transfer_with_fee_calc()` — объединяет `payments_fee`, показывает пользователю net-сумму перед `payments_transfer`
- `auto_payment_manager()` — оборачивает `auto_payments_list` + `auto_payments_delete` с переходами машины состояний

**Просмотр/корзина/поиск**
- `filter_builder()` — типизированный dict-билдер для сложных наборов параметров фильтра `category_*`
- `paginated_search()` — авто-объединение `category_*` по страницам, отдаёт items или страницы с настраиваемым лимитом
- `favorites_to_order_tracker()` — объединяет `list_favorites` + `list_orders`, находит избранные items, которые купили

**Bulk-операции**
- `bulk_edit_items()` — объединяет `managing_bulk_get` → `managing_edit` на каждый item с общим dict обновления
- `item_sync()` — один вызов `managing_bulk_get`, возвращает типизированный снапшот `{item_id: state}` для быстрых проверок

## Домен forum

**Треды**
- `thread_watcher()` — опрашивает `threads_get` на новые посты с последнего просмотренного post id, отдаёт новые id
- `thread_mark_and_leave()` — объединяет `threads_unstar` + `threads_unfollow` в одну операцию
- `claim_and_post_reply()` — объединяет `threads_claim` (как отвечающий) → атомарную публикацию ответа
- `thread_poll_tracker()` — опрашивает `threads_poll_get`, пока голосование не закроется, отдаёт финальный подсчёт

**Диалоги**
- `group_chat_invite_batch()` — объединяет `conversations_invite` для массового добавления пользователей, собирает ошибки по каждому
- `conversation_search_within()` — объединяет `conversations_search` с предфильтром `conversation_id`
- `mark_conversations_read_selective()` — объединяет `conversations_read_all` с опциональной фильтрацией по диалогу
- `message_edit_and_confirm()` — объединяет `conversations_messages_edit` + `conversations_messages_get` для верификации

**Поиск**
- `multi_search()` — диспетчеризация на `search_all`/`search_posts`/`search_threads` по параметру scope
- `search_paginator()` — авто-объединение `search_*` по страницам с настраиваемыми лимитами, отдаёт результаты
- `search_user_activity()` — объединяет `search_posts` + `search_threads` (с предзаполненным user_id), сливает хронологически

**Пользователи**
- `user_profile_complete()` — батчит `users_get` + `users_claims` + `users_likes` + `users_trophies` в один вызов
- `ignore_user_cascade()` — объединяет `users_unignore` + поиск, чтобы найти посты пользователя для массового пропуска
- `user_stats_snapshot()` — собирает `users_get` + счётчик `users_contents` + `users_followings` в одну типизированную сводку
- `batch_follow_users()` — объединяет `users_get` для верификации по каждому пользователю (нет нативного мульти-фолловинга)

**Посты/комментарии**
- `post_with_likes_check()` — объединяет `posts_get` + `users_likes` (self) для показа статуса своего лайка инлайн
- `comment_thread_crawler()` — объединяет `posts_comments_list` с пагинацией, отдаёт все комментарии по порядку
- `batch_unlike_posts()` — объединяет `posts_unlike` на каждый пост, собирает успех/провал по каждому

**Посты профиля**
- `profile_post_composer()` — объединяет `profile_posts_create`, возвращает `post_id` для последующих edit/delete
- `profile_activity_feed()` — объединяет `profile_posts_list` + `profile_posts_comments_list`, сливает в единую ленту

## Домен AntiPublic

- `bulk_check_emails()` — авто-разбивка списка email по лимиту API в 1000 строк, агрегирует результаты
- `check_and_count()` — объединяет `check_lines` → `count_lines` для показа счётчика утечек до/после
- `bulk_search_with_progress()` — оборачивает `search` чанками, отдаёт события прогресса через callback
- `email_password_validate()` — объединяет `check_lines` с комбо email+пароль, возвращает счётчик утечки

## Заметки

- 9 идей помечены 🔴 (payment/purchase/money-adjacent) — все требуют
  idempotency-ключей и явной верификации состояния перед реализацией, это не
  быстрый composite-метод.
- Каждая идея либо объединяет ≥2 сырых вызова эндпоинтов, либо закрывает
  реальный пробел сырого API (ответы только с одной страницей, нет
  bulk-delete, нет нативного поллинга).
- Вес распределён ~17 market / ~20 forum / ~4 antipublic — соответствует
  реальному размеру поверхности каждого домена.

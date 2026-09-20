# Управление сервисным центром — серверная часть

REST API информационной системы для автоматизации приёма, обработки и выдачи
заявок на ремонт техники: учёт клиентов, устройств, заявок, склада запчастей
и формирование отчётности.

**Стек:** Python 3.11 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL 15 ·
Pydantic v2 · JWT (python-jose) · passlib[bcrypt] · Docker.

---

## Быстрый запуск через Docker

```bash
git clone <адрес-репозитория> service-center
cd service-center

cp .env.example .env
# обязательно замените JWT_SECRET_KEY:
#   openssl rand -hex 32

docker compose up --build
```

После старта доступны:

| Адрес | Назначение |
|---|---|
| http://localhost:8000/docs | Swagger UI (автогенерируемая документация) |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/health | Проверка работоспособности |
| http://localhost:8000/openapi.json | Спецификация OpenAPI |

При первом запуске создаётся учётная запись администратора из переменных
`FIRST_ADMIN_*` (по умолчанию `admin` / `admin12345`). **Смените пароль сразу
после первого входа** через `PATCH /api/v1/users/{id}`.

Остановка и полная очистка данных:

```bash
docker compose down          # остановить
docker compose down -v       # остановить и удалить том с БД
```

## Запуск без Docker

Нужен работающий PostgreSQL 15+.

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# в .env укажите POSTGRES_HOST=localhost и свои реквизиты БД

uvicorn app.main:app --reload
```

---

## Первые шаги в Swagger UI

1. Откройте http://localhost:8000/docs
2. Нажмите **Authorize**, введите `admin` / `admin12345` — Swagger обратится к
   `POST /api/v1/auth/token` и подставит Bearer-токен во все запросы.
3. Создайте сотрудников: `POST /api/v1/users` (роли `manager`, `master`,
   `storekeeper`).
4. Заведите клиента: `POST /api/v1/clients`.
5. Создайте заявку: `POST /api/v1/requests`.
6. Назначьте мастера: `POST /api/v1/requests/{id}/assign`.
7. Проведите заявку по статусам: `POST /api/v1/requests/{id}/status`.

Пример входа через `curl`:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin12345"}'
```

---

## Структура проекта

```
service-center/
├── app/
│   ├── main.py              точка входа: сборка приложения, обработчики ошибок
│   ├── config.py            настройки (pydantic-settings)
│   ├── database.py          асинхронный движок и фабрика сессий
│   ├── dependencies.py      текущий пользователь, проверка ролей, пагинация
│   ├── core/
│   │   ├── security.py      хеширование паролей, выпуск и разбор JWT
│   │   ├── status_flow.py   словарь допустимых переходов статусов
│   │   ├── logging_config.py настройка логирования и аудита
│   │   └── rate_limit.py    ограничение частоты запросов к /auth
│   ├── models/              SQLAlchemy-модели
│   ├── schemas/             Pydantic-схемы (валидация и сериализация)
│   ├── services/            бизнес-логика
│   └── routers/             HTTP-эндпоинты по модулям
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

Роутеры не обращаются к БД напрямую: они валидируют вход, проверяют права через
зависимости и делегируют работу сервисам. Сервисы не знают о HTTP — они
выбрасывают доменные исключения (`app/services/exceptions.py`), которые единый
обработчик в `main.py` превращает в ответ `{"detail": "..."}`.

---

## Эндпоинты

Все пути начинаются с префикса `/api/v1`.

### Аутентификация

| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| POST | `/auth/register` | Регистрация (роль всегда «менеджер») | все |
| POST | `/auth/login` | Вход, выдача access + refresh | все |
| POST | `/auth/token` | То же через form-data (для Swagger) | все |
| POST | `/auth/refresh` | Обновление пары токенов с ротацией | все |
| POST | `/auth/logout` | Инвалидация refresh-токена | авторизованные |
| GET | `/auth/me` | Профиль текущего пользователя | авторизованные |

### Пользователи

| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| GET | `/users` | Список с фильтрами и пагинацией | admin |
| GET | `/users/masters` | Мастера и их загруженность | admin |
| POST | `/users` | Создание с любой ролью | admin |
| GET | `/users/{id}` | Просмотр | admin |
| PATCH | `/users/{id}` | Редактирование | admin |
| DELETE | `/users/{id}` | Деактивация | admin |

### Клиенты

| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| GET | `/clients` | Список, поиск по ФИО/телефону/email | admin, manager |
| POST | `/clients` | Создание | admin, manager |
| GET | `/clients/{id}` | Карточка с устройствами | admin, manager |
| PATCH | `/clients/{id}` | Редактирование | admin, manager |

### Заявки

| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| GET | `/requests` | Список с фильтрами | admin, manager, master\* |
| POST | `/requests` | Создание | admin, manager |
| GET | `/requests/{id}` | Просмотр | admin, manager, master\* |
| PATCH | `/requests/{id}` | Редактирование | admin, manager, master\* |
| POST | `/requests/{id}/assign` | Назначение мастера | admin, manager |
| POST | `/requests/{id}/status` | Смена статуса | admin, manager, master\* |
| GET | `/requests/{id}/allowed-statuses` | Доступные переходы | admin, manager, master\* |
| GET | `/requests/{id}/history` | История изменений | admin, manager, master\* |
| POST | `/requests/{id}/comments` | Комментарий | admin, manager, master\* |
| GET | `/requests/{id}/spare-parts` | Списанные запчасти | admin, manager, master\* |

\* мастер работает только с назначенными на него заявками.

### Склад

| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| GET | `/spare-parts` | Список, поиск, фильтр низких остатков | все сотрудники |
| POST | `/spare-parts` | Создание позиции | admin, storekeeper |
| GET | `/spare-parts/{id}` | Просмотр | все сотрудники |
| PATCH | `/spare-parts/{id}` | Редактирование, приход товара | admin, storekeeper |
| DELETE | `/spare-parts/{id}` | Удаление (если не было списаний) | admin, storekeeper |
| POST | `/spare-parts/{id}/write-off` | Списание на заявку | все сотрудники\*\* |

\*\* мастер списывает только на свои заявки.

### Отчёты

| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| GET | `/reports/works` | Выполненные работы за период, фильтр по мастеру | admin, manager |
| GET | `/reports/spare-parts` | Использованные запчасти | admin, manager, storekeeper |
| GET | `/reports/revenue` | Выручка по выданным заявкам | admin, manager |

Любой отчёт выгружается в CSV параметром `?format=csv`:

```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/reports/revenue?date_from=2026-01-01&group_by=month&format=csv" \
  -o revenue.csv
```

Файл кодируется в `utf-8-sig` с разделителем `;` — открывается в Excel
двойным щелчком без мастера импорта.

---

## Ключевые бизнес-правила

### Статусная модель заявки

Переходы описаны словарём `ALLOWED_STATUS_TRANSITIONS` в
`app/core/status_flow.py` — вся машина состояний в одном месте:

```
Принята ──> Диагностика ──┬──> Ожидание согласования ──┬──> В ремонте ──> Готова к выдаче ──> Выдана
                          ├──> Ожидание запчастей ─────┘         ▲                │
                          └──> В ремонте                         └────────────────┘
любой нетерминальный статус ──> Отменена
```

Переход «Принята → Выдана» вернёт `400` с перечнем доступных статусов.
«Выдана» и «Отменена» терминальны. В «В ремонте» нельзя перейти без
назначенного мастера. Выдачу и отмену подтверждает только менеджер или
администратор (`STATUS_ALLOWED_ROLES`).

Каждый переход фиксируется в журнале `status_history` с автором и временем;
при переходе в «Готова к выдаче» и «Отменена» формируется уведомление клиенту.

### Нумерация заявок

Формат `SC-YYYY-NNNN`, сквозная нумерация в пределах года. Конкурентные вставки
отсекаются уникальным индексом на колонке `number` с повтором попытки.

### Загруженность мастера

При назначении проверяется число активных (незакрытых) заявок мастера против
`MAX_ACTIVE_REQUESTS_PER_MASTER`. Список свободных исполнителей —
`GET /users/masters`.

### Склад

Остаток блокируется `SELECT ... FOR UPDATE` на время транзакции списания, поэтому
два одновременных списания не уведут количество в минус; дополнительно стоит
ограничение `CHECK (quantity >= 0)`. Цена фиксируется на момент списания
(`price_at_use`) — последующее изменение прайса не меняет выручку по уже
закрытым заявкам. При падении остатка ниже `min_quantity` формируется
уведомление.

### Телефоны клиентов

Номер нормализуется до `+7XXXXXXXXXX`, поэтому `+7 (999) 123-45-67` и
`8 999 123 45 67` распознаются как дубль (ответ `409`).

---

## Безопасность

- Пароли хранятся только в виде bcrypt-хешей; пароль длиннее 72 байт безопасно
  усекается по границе символа.
- Access-токен живёт 30 минут, refresh — 7 дней. Refresh-токены хранятся в
  таблице `refresh_tokens` и отзываются при выходе, что делает возможной
  Функцию 3 (JWT сам по себе неотзываем).
- При обновлении пары старый refresh отзывается (ротация): повторное
  использование украденного токена не сработает.
- На `/auth/*` действует ограничение частоты запросов (по умолчанию 5 попыток
  в минуту с одного IP). Реализация — в памяти процесса; при запуске нескольких
  экземпляров приложения счётчики следует вынести в Redis
  (`app/core/rate_limit.py`, интерфейс зависимости менять не потребуется).
- Ответ на неверный вход одинаков для несуществующего логина и неверного пароля —
  иначе по ответу можно перебирать существующие учётные записи.
- Защита от SQL-инъекций обеспечивается параметризацией запросов ORM.
- Контейнер приложения работает не от root.

## Коды ответов

| Код | Когда |
|---|---|
| 200 / 201 | Успех / объект создан |
| 400 | Нарушено бизнес-правило (недопустимый переход, нехватка остатка) |
| 401 | Нет токена, токен просрочен или неверные учётные данные |
| 403 | Роль не имеет прав на операцию |
| 404 | Объект не найден |
| 409 | Конфликт: дубликат логина, email, телефона, артикула |
| 422 | Ошибка валидации входных данных |
| 429 | Превышена частота запросов к `/auth` |

Формат ошибки единый: `{"detail": "сообщение"}`.

---

## Логирование

Каждый HTTP-запрос логируется с `X-Request-ID`, методом, путём, кодом ответа и
длительностью. Операции изменения данных пишутся отдельным логгером `app.audit`
через `log_action()` — фиксируется кто, что и когда изменил
(`request.status_changed`, `spare_part.written_off`, `user.created` и т.д.).

По умолчанию логи структурированы в JSON (`LOG_JSON=true`) — формат пригоден для
сбора в ELK или Loki. Для чтения глазами при разработке установите
`LOG_JSON=false`.

```bash
docker compose logs -f app
```

---

## Миграции схемы

Для разработки достаточно `AUTO_CREATE_TABLES=true`: схема создаётся при старте
приложения. Для продуктивной среды установите `false` и подключите Alembic
(зависимость уже в `requirements.txt`):

```bash
alembic init -t async migrations
# в migrations/env.py укажите target_metadata = Base.metadata
# и sqlalchemy.url из get_settings().database_url
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

## Модель данных

| Сущность | Таблица | Назначение |
|---|---|---|
| User | `users` | Сотрудники и их роли |
| Client | `clients` | Клиенты сервисного центра |
| Device | `devices` | Устройства клиентов |
| Request | `requests` | Заявки на ремонт |
| StatusHistory | `status_history` | Журнал событий заявки |
| SparePart | `spare_parts` | Номенклатура склада |
| SparePartUsage | `spare_part_usages` | Списания на заявки |
| RefreshToken | `refresh_tokens` | Выданные refresh-токены |

Все таблицы имеют `id`, `created_at`, `updated_at`. Первичный ключ —
автоинкрементный `BIGSERIAL`; обоснование выбора приведено в docstring файла
`app/models/base.py`.

Относительно модели данных из ТЗ добавлены поля, без которых не формируется
отчёт по выручке: `Request.work_cost` (стоимость работ), `Request.diagnosis` и
`Request.work_description` (результаты мастера), `SparePartUsage.price_at_use`
(цена на момент списания). Выручка = стоимость работ + стоимость списанных
запчастей по ценам списания.

## Уведомления

`app/services/notification_service.py` фиксирует уведомления в журнале. Это
точка расширения: здесь подключается реальный канал доставки (SMTP, SMS-шлюз,
push, очередь задач) без изменения вызывающего кода.

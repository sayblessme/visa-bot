# visa-bot

Telegram-бот для мониторинга визовых слотов и автозаписи на приём.

## Архитектура

```
┌─────────────┐     ┌──────────┐     ┌────────────┐
│  Telegram    │◄───►│  Bot     │     │  Celery    │
│  User        │     │ (aiogram)│     │  Worker    │
└─────────────┘     └────┬─────┘     └─────┬──────┘
                         │                  │
                    ┌────▼──────────────────▼────┐
                    │       PostgreSQL           │
                    └────────────┬───────────────┘
                                 │
                    ┌────────────▼───────────────┐
                    │   Redis (broker + backend)  │
                    └────────────────────────────┘
                                 │
                    ┌────────────▼───────────────┐
                    │    Celery Beat (scheduler)  │
                    └────────────────────────────┘
```

**Компоненты:**
- **Bot** — aiogram v3, обработка команд и inline-кнопок
- **Worker** — Celery воркеры: мониторинг слотов, бронирование (Playwright)
- **Beat** — Celery Beat: периодическая диспетчеризация мониторинга
- **Providers** — плагины для конкретных визовых центров (MockProvider + GenericPlaywrightProvider)

## Быстрый старт

### 1. Подготовка

```bash
cp .env.example .env
# Отредактируйте .env — установите BOT_TOKEN от @BotFather
```

Сгенерируйте ключ шифрования:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Вставьте результат в `SESSIONS_ENCRYPTION_KEY` в `.env`.

### 2. Запуск

```bash
docker compose up --build
```

Это поднимет:
- PostgreSQL
- Redis
- Миграции Alembic (автоматически)
- Telegram-бот
- Celery Worker
- Celery Beat

### 3. Ручной запуск (без Docker)

```bash
# Установка зависимостей
pip install -e ".[dev]"
playwright install chromium

# PostgreSQL и Redis должны быть запущены локально
# Настройте DATABASE_URL и REDIS_URL в .env

# Миграции
alembic upgrade head

# Бот
python -m app.main

# Worker (в отдельном терминале)
celery -A app.tasks.celery_app worker --loglevel=info

# Beat (в отдельном терминале)
celery -A app.tasks.celery_app beat --loglevel=info
```

## Как протестировать

### Юнит-тесты

```bash
pip install -e ".[dev]"
pytest -v
```

### Ручное тестирование с MockProvider

1. Запустите систему (`docker compose up --build`)
2. Откройте бота в Telegram, нажмите `/start`
3. Нажмите **"Выбрать страну"** → выберите любую страну
4. Нажмите **"Включить мониторинг"**
5. Подождите 1-3 минуты — MockProvider генерирует слоты с вероятностью ~30% при каждой проверке
6. Вы получите уведомление: "Найден слот! ..."

### Тест автозаписи

1. Нажмите **"Автозапись: Вкл"**
2. При нахождении следующего слота бот автоматически запустит бронирование
3. Возможные результаты MockProvider:
   - **50% — success**: "Бронирование подтверждено"
   - **30% — need_user_action**: "Пожалуйста, решите капчу..." + кнопки "Готово" / "Ввести код"
   - **20% — failed**: "Слот занят другим заявителем"
4. При `need_user_action` нажмите "Готово / Продолжить" — бронирование будет завершено
5. Нажмите **"История попыток"** для просмотра всех booking_attempts

### Тест human-in-the-loop

1. При получении сообщения "ACTION REQUIRED" с кнопками:
   - **"Готово / Продолжить"** — резюмирует booking без дополнительного ввода
   - **"Ввести код"** — бот попросит ввести код, затем резюмирует booking
   - Или отправьте `/continue` — резюмирует последнюю pending booking

## Структура проекта

```
visa-bot/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── alembic.ini
├── .env.example
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial.py
├── app/
│   ├── main.py              # Entry point (bot polling)
│   ├── config.py             # pydantic-settings
│   ├── logging.py            # structlog setup
│   ├── db/
│   │   ├── base.py           # DeclarativeBase
│   │   ├── session.py        # Engine + session factories
│   │   ├── models.py         # SQLAlchemy models
│   │   └── crud.py           # Database operations
│   ├── bot/
│   │   ├── dispatcher.py     # Bot + Dispatcher creation
│   │   ├── keyboards.py      # Reply + Inline keyboards
│   │   ├── states.py         # FSM states
│   │   ├── handlers_start.py
│   │   ├── handlers_menu.py
│   │   ├── handlers_settings.py
│   │   ├── handlers_monitoring.py
│   │   └── handlers_booking.py
│   ├── providers/
│   │   ├── base.py           # BaseProvider ABC
│   │   ├── mock.py           # MockProvider (for testing)
│   │   ├── generic_playwright.py  # Playwright template
│   │   ├── registry.py       # Provider factory
│   │   └── schemas.py        # Slot, BookingResult, MonitorCriteria
│   ├── tasks/
│   │   ├── celery_app.py     # Celery configuration
│   │   ├── beat.py           # Beat schedule
│   │   ├── monitor.py        # Monitoring tasks
│   │   └── book.py           # Booking tasks
│   └── utils/
│       ├── crypto.py         # Fernet encrypt/decrypt
│       ├── hashing.py        # Slot hash for dedup
│       └── backoff.py        # Interval calculation with jitter
└── tests/
    ├── conftest.py           # SQLite async fixture
    ├── test_hashing.py       # Slot hash tests
    ├── test_crud.py          # CRUD operations tests
    ├── test_monitor.py       # Monitor + dedup tests
    └── test_crypto.py        # Encryption tests
```

## Расширение

### Добавление нового провайдера

1. Создайте файл `app/providers/your_provider.py`
2. Наследуйтесь от `BaseProvider`
3. Реализуйте `fetch_availability()` и `book()`
4. Зарегистрируйте в `app/providers/registry.py`

```python
from app.providers.base import BaseProvider
from app.providers.schemas import Slot, BookingResult, MonitorCriteria

class YourProvider(BaseProvider):
    name = "your_center"

    async def fetch_availability(self, criteria: MonitorCriteria) -> list[Slot]:
        # Playwright automation here
        ...

    async def book(self, slot: Slot, user_profile: dict) -> BookingResult:
        # Booking flow with human-in-the-loop support
        ...
```

### GenericPlaywrightProvider

Файл `app/providers/generic_playwright.py` содержит готовый каркас с методами:
- `login()` — авторизация на сайте
- `navigate_to_calendar()` — навигация к расписанию
- `parse_slots()` — парсинг слотов
- `select_slot_and_book()` — бронирование с обработкой капчи

Замените TODO-заглушки реальными CSS-селекторами для целевого сайта.

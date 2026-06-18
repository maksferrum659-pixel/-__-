# Единая учебная среда

Telegram-бот, который сводит в одну точку **расписание** (детерминированный парсинг
портала `rr-edu.ranepa.ru`) и **дедлайны** (ИИ-извлечение из сообщений чата).

## Стек
Python 3.11+, aiogram 3.x, httpx, Supabase (Postgres), APScheduler, GigaChat,
Fernet (`cryptography`), pydantic v2. Источник истины — [CONTRACT.md](CONTRACT.md).

## Структура
```
shared/   модели данных (ScheduleEvent, Deadline)
core/     security (Fernet) · llm (GigaChat) · deadline_extractor (ИИ)
parser/   логин на портал + fetch_schedule → ScheduleEvent
db/        публичный API Supabase + миграции
bot/       aiogram: команды, FSM, планировщик (синк + напоминания)
tests/     test_parser (офлайн) · test_bot (офлайн) · test_db (интеграция)
```

## Быстрый старт
```bash
python -m pip install -r requirements.txt
cp .env.example .env        # заполнить секреты (CONTRACT.md §8)
pytest tests/test_parser.py tests/test_bot.py   # офлайн-тесты
python -m bot.main          # запуск бота
```

Подробнее об архитектуре, потоке данных и зонах ответственности — в [CLAUDE.md](CLAUDE.md).

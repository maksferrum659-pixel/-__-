# CONTRACT.md — источник истины проекта «Единая учебная среда»

> Этот файл — **общий и замороженный**. Он лежит в `main` и одинаков во всех ветках.
> Любая ветка читает его ПЕРВЫМ. Менять его в одиночку нельзя — только командным
> решением через PR в `main`, помеченный `[contract]`. Несогласованное изменение
> моделей или сигнатур ломает merge у всех.

## 1. Что мы строим
Telegram-бот, который сводит в одну точку: **расписание** (детерминированный парсинг
портала `rr-edu.ranepa.ru`) и **дедлайны** (ИИ-извлечение из сообщений TG-чата).
Расписание — персональное (per-user auth на портале). Дедлайны — групповые (один
бот читает чат и пишет общие дедлайны для всех участников).

## 2. Стек (фиксирован, не обсуждается в ветках)
- Python 3.11+, `pydantic` v2 — модели данных
- `aiogram` 3.x — бот
- `httpx` — запросы к порталу
- `supabase` (supabase-py) — доступ к БД
- `APScheduler` — синк расписания и рассылка напоминаний
- LLM: **GigaChat** (запасной — YandexGPT), вызов через `core/llm.py`
- `cryptography` (Fernet) — шифрование токена портала

## 3. Структура репозитория (монорепо)
```
/shared/        ОБЩЕЕ, frozen. Модели данных. Меняется только командно.
  models.py
/core/          ОБЩЕЕ, frozen. ИИ-ядро + утилиты.
  deadline_extractor.py   (готов)
  llm.py                  (клиент LLM под протокол LLMClient)
  security.py             (Fernet encrypt/decrypt токена)
/db/            ВЕТКА НАСТИ. Реализация. Публичный API заморожен в §6.
  __init__.py             (экспортирует функции из §6)
  client.py
  migrations/*.sql
/parser/        ВЕТКА МАКСИМА. Реализация. Публичный API заморожен в §6.
  __init__.py
  portal.py
/bot/           ВЕТКА ЕГОРА. Реализация.
  main.py
  handlers.py
  scheduler.py
/tests/
.env.example
```
**Правило веток:** каждый трогает в основном свою папку. `shared/`, `core/`,
`db/migrations/` правятся только по согласованию. Это сводит merge-конфликты к нулю.

## 4. Поток данных
```
портал --parser.fetch_schedule()--> [ScheduleEvent] --db.upsert_schedule_events--> Supabase
TG-чат --bot handler--> core.extract_deadline() --> Deadline --db.upsert_deadline--> Supabase
бот команды (/today /week ...) --> db.get_* --> ответ пользователю
APScheduler --> sync расписания + рассылка напоминаний по дедлайнам
```

## 5. Модели данных (`shared/models.py`) — КОНТРАКТ, не менять в ветке
```python
from datetime import datetime
from pydantic import BaseModel

class ScheduleEvent(BaseModel):
    external_id: str          # id события из портала (для идемпотентного upsert)
    telegram_id: int          # чьё это персональное расписание
    discipline_name: str
    kind: str | None = None   # "лекция" | "семинар" | ...
    starts_at: datetime       # tz-aware (Europe/Moscow)
    ends_at: datetime
    room: str | None = None
    teacher: str | None = None
    online_link: str | None = None

class Deadline(BaseModel):
    chat_id: int              # групповой чат-источник (дедлайн групповой)
    discipline_name: str | None = None
    work_type: str | None = None     # "ДЗ" | "реферат" | "презентация" | "зачёт"...
    due_at: datetime | None = None   # дата+время дедлайна; None если срок не извлечён
    raw_quote: str | None = None
    confidence: float = 0.0
    source_message_id: int | None = None
    id: str | None = None     # заполняет БД при вставке
```
`DeadlineExtraction` (выход ИИ-ядра) определён в `core/deadline_extractor.py` —
маппинг в `Deadline` делает вызывающая сторона (бот).

## 6. Публичные API (сигнатуры заморожены; реализацию пишут владельцы веток)

### db (владелец — Настя). Все остальные ТОЛЬКО импортируют это:
```python
def get_or_create_user(telegram_id: int) -> dict: ...
def save_portal_token(telegram_id: int, encrypted_token: str) -> None: ...
def get_portal_token(telegram_id: int) -> str | None: ...
def upsert_schedule_events(telegram_id: int, events: list[ScheduleEvent]) -> int: ...
def get_schedule(telegram_id: int, since: datetime, until: datetime) -> list[ScheduleEvent]: ...
def upsert_deadline(deadline: Deadline) -> Deadline: ...           # дедуп по (chat_id, source_message_id)
def list_deadlines(chat_id: int, only_open: bool = True) -> list[Deadline]: ...
def mark_deadline_done(telegram_id: int, deadline_id: str, done: bool) -> None: ...
def list_users_with_token() -> list[int]: ...                      # для sync-задачи
```

### parser (владелец — Максим). Чистая библиотека, в БД НЕ пишет:
```python
def authenticate(login: str, password: str) -> str: ...            # вернуть session token/cookie-строку
def fetch_schedule(token: str, since: date, until: date) -> list[ScheduleEvent]: ...
```

### core (общее, frozen):
```python
# deadline_extractor.py
def extract_deadline(message_text: str, client: LLMClient, today: date) -> DeadlineExtraction: ...
# llm.py
class GigaChatClient:  # реализует протокол LLMClient: .complete(system, user) -> str
    ...
# security.py
def encrypt_token(plain: str) -> str: ...
def decrypt_token(enc: str) -> str: ...
```

## 7. Схема Supabase (владелец — Настя; здесь как контракт)
```sql
users(telegram_id bigint primary key, portal_token_encrypted text, created_at timestamptz default now());
disciplines(id uuid default gen_random_uuid() primary key, name text unique, control_form text, online_link text);
schedule_events(external_id text, telegram_id bigint references users, discipline_name text,
                kind text, starts_at timestamptz, ends_at timestamptz, room text, teacher text,
                online_link text, primary key(external_id, telegram_id));
deadlines(id uuid default gen_random_uuid() primary key, chat_id bigint, discipline_name text,
          work_type text, due_at timestamptz, raw_quote text, confidence real,
          source_message_id bigint, created_at timestamptz default now(),
          unique(chat_id, source_message_id));
user_deadline_status(telegram_id bigint references users, deadline_id uuid references deadlines,
                     done boolean default false, primary key(telegram_id, deadline_id));
```
RLS включить; токен НЕ хранить открытым (Fernet на стороне приложения).

## 8. Переменные окружения (`.env.example`)
```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
BOT_TOKEN=
GIGACHAT_CREDENTIALS=
FERNET_KEY=
PORTAL_BASE_URL=https://rr-edu.ranepa.ru
```

## 9. Git-дисциплина
- Ветки: `parser`, `bot`, `db` (от `main`). Интеграция — PR в `main` (или `develop`) часто и мелко.
- `shared/`, `core/`, `db/migrations/`, `CONTRACT.md` — read-only для веток, правка только PR `[contract]`.
- Перед мержем: `pytest` зелёный, импорты соответствуют §5–§6.
- Конфликт в общих файлах = сигнал, что нарушен контракт. Не «разрешаем» молча — обсуждаем.

## 10. Определение готовности (DoD)
- **parser**: `fetch_schedule` возвращает `list[ScheduleEvent]` на реальном аккаунте; есть тест на парсинг сохранённого JSON-ответа.
- **db**: все функции §6 работают против Supabase; миграции применяются с нуля; RLS настроен.
- **bot**: команды `/today /week /discipline /credits` отвечают; приём сообщений чата → `extract_deadline` → `upsert_deadline`; sync расписания и напоминания по расписанию работают.

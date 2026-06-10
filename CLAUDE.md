# CLAUDE.md — ветка `db` (Настя)

## Перед началом
1. Прочитай `CONTRACT.md` — источник истины. Твои §6 (db API) и §7 (схема) — это контракт, на который опираются Максим и Егор.
2. Работаешь **в `/db/`**. Модели `shared/models.py` не меняешь в одиночку (PR `[contract]`).

## Твоя зона ответственности
База данных в **Supabase** (Postgres): схема, миграции, RLS, безопасное хранение
токена портала, и **публичный Python-API** (`db/__init__.py`), который импортируют
бот и sync-задача. Внешний код НЕ должен знать про SQL/Supabase — только твои функции.

## Что реализовать
### `/db/migrations/*.sql` — схема строго по §7 контракта:
`users`, `disciplines`, `schedule_events`, `deadlines`, `user_deadline_status`.
- `gen_random_uuid()` для id; уникальные ключи для идемпотентности
  (`schedule_events` PK `(external_id, telegram_id)`; `deadlines` unique `(chat_id, source_message_id)`).
- Включить **RLS** на всех таблицах.
- Токен портала хранится только зашифрованным (поле `portal_token_encrypted`).
  Шифрование делает приложение через `core/security.py` — БД хранит готовый шифртекст.
  (Опционально можно усилить через pgcrypto/Supabase Vault — но не вместо app-шифрования.)

### `/db/__init__.py` — публичный API, сигнатуры заморожены в §6:
```python
get_or_create_user(telegram_id) -> dict
save_portal_token(telegram_id, encrypted_token) -> None
get_portal_token(telegram_id) -> str | None
upsert_schedule_events(telegram_id, events: list[ScheduleEvent]) -> int
get_schedule(telegram_id, since, until) -> list[ScheduleEvent]
upsert_deadline(deadline: Deadline) -> Deadline      # дедуп по (chat_id, source_message_id)
list_deadlines(chat_id, only_open=True) -> list[Deadline]
mark_deadline_done(telegram_id, deadline_id, done) -> None
list_users_with_token() -> list[int]
```
- На вход/выход — модели из `shared/models.py`, не сырые словари (кроме `get_or_create_user`).
- `/db/client.py` — инициализация `create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)` из `.env`.
- `upsert_*` должны быть идемпотентны (повторный вызов не плодит дубликаты).

## Тесты (`/tests/test_db.py`)
- CRUD по каждой функции против тестового Supabase-проекта (или локального Postgres).
- Идемпотентность upsert: двойная вставка одного события/дедлайна не создаёт дубль.
- Маппинг строк БД ↔ `ScheduleEvent` / `Deadline`.

## Чего НЕ делать
- Не реализовывать бизнес-логику бота или парсинг — только хранение и доступ.
- Не менять сигнатуры §6 и модели §5 в одиночку — это сломает Максима и Егора. Только PR `[contract]`.
- Не возвращать наружу сырые объекты Supabase — оборачивай в модели.

## Готово, когда
Миграции применяются с нуля, RLS включён, все функции §6 работают и идемпотентны, тесты зелёные.

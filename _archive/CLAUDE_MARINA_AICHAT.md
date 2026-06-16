# Бриф для Claude: ИИ-чат-бот «Ответы из чата»

> Марина, открой этот файл и скажи своему Claude:
> **«Прочитай CLAUDE_MARINA_AICHAT.md и реализуй всё что там написано»**

---

## Контекст проекта

Telegram-бот для студентов РАНХИГС. Стек: Python, aiogram 3.x, Supabase, GigaChat, APScheduler.

Групповой бот уже добавлен в чат группы и слушает все сообщения. Сейчас он только извлекает дедлайны через GigaChat. Твоя задача — добавить **память чата** и **свободный диалог** с ботом.

---

## Что нужно реализовать

### Сценарий использования

Студент пишет боту в личку (или упоминает его в группе):
> «Что нужно сдать для зачёта по психологии?»

Бот:
1. Ищет в сохранённых сообщениях группового чата всё, что связано с психологией и зачётом
2. Передаёт найденные цитаты в GigaChat
3. Получает чёткий структурированный ответ
4. Отвечает студенту

---

## Часть 1 — База данных

### Миграция 005 (создать файл `db/migrations/005_add_group_messages.sql`)

```sql
-- Миграция 005: хранение сообщений группового чата для ИИ-поиска
-- Применить ПОСЛЕ 001_init.sql

CREATE TABLE IF NOT EXISTS group_messages (
    id          uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    chat_id     bigint NOT NULL,
    message_id  bigint NOT NULL,
    sender_name text,
    text        text NOT NULL,
    sent_at     timestamptz DEFAULT now(),
    UNIQUE (chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS group_messages_chat_idx ON group_messages(chat_id);
CREATE INDEX IF NOT EXISTS group_messages_sent_idx ON group_messages(sent_at DESC);

ALTER TABLE group_messages ENABLE ROW LEVEL SECURITY;
```

### Функции в `db/__init__.py` (добавить в конец файла)

```python
def save_group_message(chat_id: int, message_id: int, sender_name: str, text: str) -> None:
    """Сохранить сообщение из группового чата."""
    supabase.table("group_messages").upsert({
        "chat_id": chat_id,
        "message_id": message_id,
        "sender_name": sender_name or "Неизвестный",
        "text": text,
    }, on_conflict="chat_id,message_id").execute()


def search_group_messages(chat_id: int, query: str, limit: int = 30) -> list[dict]:
    """Полнотекстовый поиск по сообщениям чата."""
    # Ищем по каждому слову запроса (ilike)
    words = [w.strip() for w in query.lower().split() if len(w.strip()) > 2]
    if not words:
        return []
    result = supabase.table("group_messages") \
        .select("sender_name, text, sent_at") \
        .eq("chat_id", chat_id) \
        .ilike("text", f"%{words[0]}%") \
        .order("sent_at", desc=True) \
        .limit(limit) \
        .execute()
    return result.data
```

---

## Часть 2 — Сохранение всех сообщений группы

В файле `bot/handlers.py` найди функцию `on_group_message` и добавь сохранение сообщения ДО логики дедлайнов:

```python
@router.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def on_group_message(message: Message, settings: Settings) -> None:
    # Сохраняем сообщение в историю чата
    if message.text and len(message.text) > 5:
        sender = message.from_user.full_name if message.from_user else "Неизвестный"
        db.save_group_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
            sender_name=sender,
            text=message.text,
        )

    # ... существующий код извлечения дедлайнов остаётся без изменений ...
```

---

## Часть 3 — ИИ-поиск по истории чата

### Новая функция в `core/` (создать файл `core/chat_search.py`)

```python
"""Поиск по истории группового чата через GigaChat."""
from __future__ import annotations

from core.llm import GigaChatClient

SYSTEM_PROMPT = """Ты помощник студентов РАНХИГС. Тебе дают сообщения из группового чата студентов и вопрос.
Твоя задача — найти в этих сообщениях ответ на вопрос и изложить его чётко и структурированно.
Если ответа в сообщениях нет — честно скажи об этом.
Отвечай на русском языке. Будь краток и конкретен."""

def answer_from_chat_history(
    question: str,
    messages: list[dict],
    llm: GigaChatClient,
) -> str:
    """Сформировать ответ на вопрос на основе истории чата."""
    if not messages:
        return "В истории чата не нашлось информации по этому вопросу. Попробуй спросить по-другому."

    context = "\n".join(
        f"[{m.get('sender_name', '?')}]: {m.get('text', '')}"
        for m in messages[:25]  # берём не больше 25 сообщений
    )

    prompt = (
        f"Сообщения из чата студентов:\n\n{context}\n\n"
        f"Вопрос студента: {question}\n\n"
        "Дай чёткий ответ на основе этих сообщений."
    )

    return llm.complete(prompt, system=SYSTEM_PROMPT)
```

### Метод `complete` в `core/llm.py`

Проверь, есть ли в `GigaChatClient` метод `complete(prompt, system)`. Если нет — добавь:

```python
def complete(self, prompt: str, system: str | None = None) -> str:
    """Получить ответ от GigaChat на произвольный запрос."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    # используй существующий метод вызова GigaChat API из этого же файла
    return self._call(messages)
```

---

## Часть 4 — Хендлер для вопросов в личке

В `bot/handlers.py` добавить новое FSM-состояние и хендлер:

```python
class ChatQuestion(StatesGroup):
    """FSM для вопроса к ИИ по истории чата."""
    waiting_question = State()
    waiting_chat_id = State()
```

Добавить кнопку в нижнюю клавиатуру (`_commands_keyboard`):
```python
[KeyboardButton(text="💬 Спросить ИИ"), KeyboardButton(text="📆 Неделя")],
```

Добавить хендлеры:

```python
@router.message(F.text == "💬 Спросить ИИ", F.chat.type == "private")
async def btn_ask_ai(message: Message, state: FSMContext) -> None:
    await state.set_state(ChatQuestion.waiting_question)
    await message.answer(
        "Задай вопрос — я поищу ответ в истории вашего группового чата.\n\n"
        "Например: «Что нужно для зачёта по психологии?» или «Когда сдавать реферат по экономике?»"
    )


@router.message(ChatQuestion.waiting_question, F.chat.type == "private", F.text)
async def on_ai_question(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    question = message.text.strip()
    await message.answer("🔍 Ищу в истории чата…")

    # Получить chat_id группы пользователя
    # (нужно хранить chat_id группы, к которой привязан пользователь)
    group_chat_id = db.get_group_chat_id(message.from_user.id)
    if not group_chat_id:
        await message.answer(
            "Не знаю, в каком чате ты состоишь. "
            "Попроси добавить бота в вашу группу в Telegram и напиши там любое сообщение."
        )
        return

    messages_found = db.search_group_messages(group_chat_id, question)
    from core.chat_search import answer_from_chat_history
    answer = answer_from_chat_history(question, messages_found, _llm)
    await message.answer(f"🤖 <b>Ответ из чата:</b>\n\n{answer}")
```

---

## Часть 5 — Привязка пользователя к групповому чату

Нужно хранить, в каком групповом чате состоит каждый пользователь.

### Миграция 006 (создать `db/migrations/006_add_group_chat_id.sql`)

```sql
-- Миграция 006: групповой чат пользователя
ALTER TABLE users ADD COLUMN IF NOT EXISTS group_chat_id bigint;
```

### Функции в `db/__init__.py`

```python
def save_group_chat_id(telegram_id: int, chat_id: int) -> None:
    """Сохранить ID группового чата пользователя."""
    supabase.table("users").upsert({
        "telegram_id": telegram_id,
        "group_chat_id": chat_id,
    }, on_conflict="telegram_id").execute()


def get_group_chat_id(telegram_id: int) -> int | None:
    result = supabase.table("users").select("group_chat_id").eq(
        "telegram_id", telegram_id
    ).execute()
    if result.data:
        return result.data[0].get("group_chat_id")
    return None
```

### Автоматическое определение чата

В `on_group_message` добавь привязку пользователя к чату:

```python
# Привязываем пользователя к чату (если ещё не привязан)
if message.from_user:
    db.save_group_chat_id(message.from_user.id, message.chat.id)
```

---

## Порядок реализации

1. Создать `db/migrations/005_add_group_messages.sql` и `006_add_group_chat_id.sql`
2. Добавить функции в `db/__init__.py`
3. Создать `core/chat_search.py`
4. Проверить/добавить метод `complete` в `core/llm.py`
5. Обновить `bot/handlers.py` — сохранение сообщений + хендлер вопросов + кнопка
6. **Сказать Насте** применить миграции 005 и 006 в Supabase SQL Editor

---

## Важные детали

- **Не сохраняй короткие сообщения** (< 5 символов) и команды (начинаются с `/`)
- **Лимит поиска** — не передавай в GigaChat больше 25 сообщений (контекстное окно)
- **Не трогай** `shared/`, `core/security.py`, `parser/`, `db/migrations/001_init.sql`
- **Миграции** применяет Настя — создай файлы, но не запускай сам
- Все новые зависимости добавь в `requirements.txt`

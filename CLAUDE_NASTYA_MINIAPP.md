# Бриф для Claude: Telegram Mini App — «Единая учебная среда»

> Это инструкция для Claude Code. Настя, открой этот файл и скажи своему Claude:
> **«Прочитай CLAUDE_NASTYA_MINIAPP.md и реализуй всё что там написано»**

---

## Контекст проекта

Мы делаем Telegram-бот для студентов РАНХИГС. Стек:
- **Бэкенд:** Python, FastAPI (уже есть в `ical/server.py`), Supabase
- **Бот:** aiogram 3.x
- **База данных:** Supabase (PostgreSQL)

Твоя задача — добавить **Telegram Mini App**: красивый веб-интерфейс, который открывается прямо внутри Telegram по кнопке от бота.

---

## Схема базы данных (для понимания данных)

```sql
schedule_events (
    telegram_id, discipline_name, kind,
    starts_at, ends_at, room, teacher, online_link
)

deadlines (
    id uuid, chat_id, discipline_name,
    work_type, due_at, raw_quote, confidence
)

user_deadline_status (
    telegram_id, deadline_id, done boolean
)
```

---

## Что нужно построить

### Часть 1 — Фронтенд (новая папка `mini_app/`)

React-приложение (Vite + React) с тремя экранами и нижней навигацией.

#### Экран 1: «Сегодня»
- Текущая пара (если идёт прямо сейчас) — выделена большой карточкой
- Следующие пары сегодня — список карточек
- Дедлайны на сегодня и завтра — внизу секцией

#### Экран 2: «Неделя»
- Горизонтальный свайп по дням (Пн — Вс)
- Активный день подсвечен
- Каждый день — список пар с временем, аудиторией, преподавателем

#### Экран 3: «Дедлайны»
- Список всех дедлайнов, сгруппированных по дате
- Чекбокс «выполнено» на каждом
- Просроченные — красные, срочные (до 2 дней) — жёлтые, остальные — обычные

#### Дизайн (обязательно)
Использовать CSS-переменные Telegram для нативного вида:
```css
var(--tg-theme-bg-color)
var(--tg-theme-text-color)
var(--tg-theme-hint-color)
var(--tg-theme-button-color)
var(--tg-theme-button-text-color)
var(--tg-theme-secondary-bg-color)
```
Карточки с тенью. Плавные анимации. Нижняя навигация с иконками.

#### Структура файлов
```
mini_app/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── api.js
    ├── components/
    │   ├── BottomNav.jsx
    │   ├── EventCard.jsx
    │   └── DeadlineCard.jsx
    └── screens/
        ├── TodayScreen.jsx
        ├── WeekScreen.jsx
        └── DeadlinesScreen.jsx
```

#### Инициализация Telegram WebApp (в App.jsx)
```js
// В index.html добавить:
// <script src="https://telegram.org/js/telegram-web-app.js"></script>

const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const initData = tg.initData; // передаём в каждый запрос
```

---

### Часть 2 — Бэкенд (расширить `ical/server.py`)

#### Проверка initData
```python
import hashlib, hmac, urllib.parse, os
from fastapi import Header, HTTPException

def verify_init_data(init_data: str) -> int:
    bot_token = os.environ["BOT_TOKEN"]
    parsed = dict(urllib.parse.parse_qsl(init_data))
    received_hash = parsed.pop("hash", "")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise HTTPException(status_code=401, detail="Невалидный initData")
    import json
    return json.loads(parsed["user"])["id"]
```

#### Новые роуты
```python
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/schedule/today")
def get_today(x_init_data: str = Header(...)):
    telegram_id = verify_init_data(x_init_data)
    now = datetime.now(_TZ)
    start = now.replace(hour=0, minute=0, second=0)
    end = now.replace(hour=23, minute=59, second=59)
    events = db.get_schedule(telegram_id, start, end)
    return [e.__dict__ for e in events]

@app.get("/api/schedule/week")
def get_week(x_init_data: str = Header(...)):
    telegram_id = verify_init_data(x_init_data)
    now = datetime.now(_TZ)
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    events = db.get_schedule(telegram_id, monday.replace(hour=0, minute=0), sunday.replace(hour=23, minute=59))
    return [e.__dict__ for e in events]

@app.get("/api/deadlines")
def get_deadlines(x_init_data: str = Header(...)):
    telegram_id = verify_init_data(x_init_data)
    return [d.__dict__ for d in db.list_deadlines(telegram_id)]

@app.post("/api/deadlines/{deadline_id}/done")
def mark_done(deadline_id: str, x_init_data: str = Header(...)):
    telegram_id = verify_init_data(x_init_data)
    db.set_deadline_done(telegram_id, deadline_id, done=True)
    return {"ok": True}

@app.post("/api/deadlines/{deadline_id}/undone")
def mark_undone(deadline_id: str, x_init_data: str = Header(...)):
    telegram_id = verify_init_data(x_init_data)
    db.set_deadline_done(telegram_id, deadline_id, done=False)
    return {"ok": True}

# Раздавать собранный фронтенд
from fastapi.staticfiles import StaticFiles
app.mount("/mini_app", StaticFiles(directory="mini_app/dist", html=True), name="mini_app")
```

---

### Часть 3 — Кнопка в боте (`bot/handlers_personal.py`)

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

MINI_APP_URL = "https://ТВОЙ_ДОМЕН/mini_app/"

@router.message(Command("app"))
async def cmd_app(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Открыть расписание",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )
    ]])
    await message.answer("Нажми кнопку ниже:", reply_markup=kb)
```

---

### Часть 4 — Новая функция в `db/__init__.py`

```python
def set_deadline_done(telegram_id: int, deadline_id: str, done: bool) -> None:
    _client().table("user_deadline_status").upsert({
        "telegram_id": telegram_id,
        "deadline_id": deadline_id,
        "done": done,
    }).execute()
```

---

## Порядок реализации

1. `npm create vite@latest mini_app -- --template react` — создать фронтенд
2. Реализовать три экрана и нижнюю навигацию
3. Подключить `window.Telegram.WebApp` и передавать `initData` в запросы
4. Расширить `ical/server.py` новыми роутами и CORS
5. Добавить `set_deadline_done` в `db/__init__.py`
6. Добавить команду `/app` в `bot/handlers_personal.py`
7. Добавить в `.gitignore`: `mini_app/node_modules/` и `mini_app/dist/`

---

## Важные детали

- **Mini App работает только по HTTPS.** Для тестирования использовать ngrok.
- **initData валидна 24 часа** — бэкенд обязан проверять подпись через HMAC.
- **Стили:** только Telegram CSS-переменные + custom CSS. Никакого Bootstrap/MUI.
- **Не трогать:** `shared/`, `core/`, `parser/`, `db/migrations/` — чужие зоны.
- **Не коммитить:** `node_modules/`, `mini_app/dist/`, `.env`

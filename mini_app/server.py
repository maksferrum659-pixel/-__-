"""FastAPI-сервер для Telegram Mini App.

Запуск: uvicorn mini_app.server:app --host 0.0.0.0 --port 8000
Для прода нужен HTTPS (ngrok для тестов: ngrok http 8000).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    pass

import db

_TZ = ZoneInfo("Europe/Moscow")
_HERE = Path(__file__).parent
_CREDIT_KINDS = {
    "зачёт", "зачет", "экзамен", "зачет с оценкой", "зачёт с оценкой",
    "дифференцированный зачёт", "дифференцированный зачет",
}

app = FastAPI(title="Учёба Бот — Mini App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _verify_init_data(init_data: str) -> int:
    """Проверить HMAC-подпись Telegram initData, вернуть telegram_id."""
    bot_token = os.environ.get("BOT_TOKEN", "")
    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", "")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise HTTPException(status_code=401, detail="Невалидный initData")
    user = json.loads(parsed.get("user", "{}"))
    telegram_id = user.get("id")
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Нет user.id в initData")
    return int(telegram_id)


# ── Расписание ────────────────────────────────────────────────────────────────

@app.get("/api/schedule/today")
def get_today(x_init_data: str = Header(..., alias="x-init-data")):
    telegram_id = _verify_init_data(x_init_data)
    now = datetime.now(_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    events = db.get_schedule(telegram_id, start, end)
    return [e.model_dump(mode="json") for e in events]


@app.get("/api/schedule/week")
def get_week(x_init_data: str = Header(..., alias="x-init-data")):
    telegram_id = _verify_init_data(x_init_data)
    now = datetime.now(_TZ)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    events = db.get_schedule(telegram_id, monday, sunday)
    return [e.model_dump(mode="json") for e in events]


# ── Зачёты/экзамены ──────────────────────────────────────────────────────────

@app.get("/api/exams")
def get_exams(x_init_data: str = Header(..., alias="x-init-data")):
    telegram_id = _verify_init_data(x_init_data)
    now = datetime.now(_TZ)
    events = db.get_schedule(telegram_id, now, now + timedelta(days=120))
    events = [e for e in events if e.kind and any(k in e.kind.lower() for k in _CREDIT_KINDS)]
    chat_id = db.get_group_chat_id(telegram_id)
    deadlines = db.list_deadlines(chat_id, only_open=True) if chat_id else []
    deadlines = [d for d in deadlines if d.work_type and d.work_type.lower() in _CREDIT_KINDS]
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "deadlines": [d.model_dump(mode="json") for d in deadlines],
    }


# ── Поиск по предмету ────────────────────────────────────────────────────────

@app.get("/api/subjects")
def get_subjects(x_init_data: str = Header(..., alias="x-init-data")):
    telegram_id = _verify_init_data(x_init_data)
    now = datetime.now(_TZ)
    events = db.get_schedule(telegram_id, now, now + timedelta(days=30))
    chat_id = db.get_group_chat_id(telegram_id)
    deadlines = db.list_deadlines(chat_id, only_open=True) if chat_id else []
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "deadlines": [d.model_dump(mode="json") for d in deadlines],
    }


# ── Дедлайны ──────────────────────────────────────────────────────────────────

@app.get("/api/deadlines")
def get_deadlines(x_init_data: str = Header(..., alias="x-init-data")):
    telegram_id = _verify_init_data(x_init_data)
    chat_id = db.get_group_chat_id(telegram_id)
    if not chat_id:
        return []
    deadlines = db.list_deadlines(chat_id, only_open=True)
    return [d.model_dump(mode="json") for d in deadlines]


@app.post("/api/deadlines/{deadline_id}/done")
def mark_done(deadline_id: str, x_init_data: str = Header(..., alias="x-init-data")):
    telegram_id = _verify_init_data(x_init_data)
    db.mark_deadline_done(telegram_id, deadline_id, done=True)
    return {"ok": True}


@app.post("/api/deadlines/{deadline_id}/undone")
def mark_undone(deadline_id: str, x_init_data: str = Header(..., alias="x-init-data")):
    telegram_id = _verify_init_data(x_init_data)
    db.mark_deadline_done(telegram_id, deadline_id, done=False)
    return {"ok": True}


# ── Фронтенд ──────────────────────────────────────────────────────────────────

@app.get("/")
@app.get("/mini_app")
def serve_index():
    return FileResponse(_HERE / "index.html")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MINI_APP_PORT", "8000"))
    uvicorn.run("mini_app.server:app", host="0.0.0.0", port=port, reload=False)

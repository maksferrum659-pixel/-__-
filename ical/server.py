"""FastAPI-сервер для отдачи ICS-фида по уникальному токену пользователя."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

import db
from .generator import events_to_ics

_TZ = ZoneInfo("Europe/Moscow")


def make_app(base_url: str) -> FastAPI:
    """Создать FastAPI-приложение. Запускается рядом с ботом через uvicorn.Server."""
    app = FastAPI(title="ICS-фид расписания", docs_url=None, redoc_url=None)

    @app.get("/ical/{token}.ics")
    def get_ical(token: str) -> Response:
        telegram_id = db.get_telegram_id_by_ical_token(token)
        if telegram_id is None:
            raise HTTPException(status_code=404, detail="Токен не найден")

        now = datetime.now(_TZ)
        events = db.get_schedule(telegram_id, now - timedelta(days=14), now + timedelta(days=90))
        deadlines = db.list_deadlines(telegram_id)

        content = events_to_ics(events, deadlines)
        return Response(
            content=content,
            media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="schedule.ics"'},
        )

    return app

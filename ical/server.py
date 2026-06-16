"""FastAPI-сервер для отдачи ICS-фида по уникальному токену пользователя.

Реализовать:
  make_app(base_url: str) -> FastAPI

Эндпоинт:
  GET /ical/{token}.ics
    - Проверяет токен через db.get_telegram_id_by_ical_token(token)
    - 404 если токен не найден
    - Берёт события за -14 дней..+90 дней
    - Возвращает text/calendar с ICS-содержимым

Запуск рядом с ботом — через asyncio.gather в bot/main.py:
  config = uvicorn.Config(make_app(settings.calendar_base_url), host="0.0.0.0", port=8080)
  await uvicorn.Server(config).serve()

Зависимости: fastapi>=0.110.0, uvicorn>=0.29.0
"""
from __future__ import annotations


def make_app(base_url: str):
    """Создать FastAPI-приложение для ICS-фида."""
    raise NotImplementedError("TODO: Marina — реализовать HTTP-сервер ICS")

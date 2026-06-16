"""
ICS-экспорт расписания (CONTRACT.md §10).

    events_to_ics(events, deadlines) -> str   — генератор iCalendar
    make_app(base_url)               -> FastAPI — HTTP-сервер /ical/{token}.ics
"""
from .generator import events_to_ics
from .server import make_app

__all__ = ["events_to_ics", "make_app"]

"""ICS-экспорт расписания (CONTRACT.md §10).

    events_to_ics(events, deadlines) -> str   — генератор iCalendar
"""
from .generator import events_to_ics

__all__ = ["events_to_ics"]

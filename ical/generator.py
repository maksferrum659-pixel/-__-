"""Генератор iCalendar (RFC 5545) из моделей проекта.

Реализовать:
  events_to_ics(events, deadlines, calendar_name) -> str

Маппинг:
  ScheduleEvent -> VEVENT (дата, время, аудитория, преподаватель, ссылка)
  Deadline      -> VEVENT (срок сдачи) + VALARM за 24ч и 1ч
  kind=Зачёт/Экзамен -> CATEGORIES:Зачёт / Экзамен

Библиотека: icalendar>=5.0.0
"""
from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.models import Deadline, ScheduleEvent


def events_to_ics(
    events: list[ScheduleEvent],
    deadlines: list[Deadline],
    calendar_name: str = "Расписание",
) -> str:
    """Конвертировать события и дедлайны в строку формата iCalendar."""
    raise NotImplementedError("TODO: Marina — реализовать генератор ICS")

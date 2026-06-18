"""Генератор iCalendar (RFC 5545) из моделей проекта."""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from icalendar import Alarm, Calendar, Event

if TYPE_CHECKING:
    from shared.models import Deadline, ScheduleEvent

_EXAM_KINDS = {"зачёт", "зачет", "экзамен"}


def events_to_ics(
    events: list[ScheduleEvent],
    deadlines: list[Deadline],
    calendar_name: str = "Расписание",
) -> str:
    """Конвертировать события и дедлайны в строку iCalendar."""
    cal = Calendar()
    cal.add("prodid", "-//Единая учебная среда//RU")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", calendar_name)
    cal.add("x-wr-timezone", "Europe/Moscow")

    for ev in events:
        cal.add_component(_schedule_to_vevent(ev))

    for dl in deadlines:
        vevent = _deadline_to_vevent(dl)
        if vevent is not None:
            cal.add_component(vevent)

    return cal.to_ical().decode("utf-8")


def _schedule_to_vevent(ev: ScheduleEvent) -> Event:
    kind = ev.kind or ""
    summary = f"{ev.discipline_name} ({kind})" if kind else ev.discipline_name

    vevent = Event()
    vevent.add("summary", summary)
    vevent.add("dtstart", ev.starts_at)
    vevent.add("dtend", ev.ends_at)
    vevent.add("uid", f"sched-{ev.external_id}-{ev.telegram_id}@orel-edu")

    if ev.room:
        vevent.add("location", ev.room)
    if ev.teacher:
        vevent.add("description", ev.teacher)
    if ev.online_link:
        vevent.add("url", ev.online_link)
    if kind and kind.lower() in _EXAM_KINDS:
        vevent.add("categories", kind)

    return vevent


def _deadline_to_vevent(dl: Deadline) -> Event | None:
    if not dl.due_at:
        return None

    work = dl.work_type or ""
    name = dl.discipline_name or "Дедлайн"
    summary = f"{work}: {name}" if work else name

    vevent = Event()
    vevent.add("summary", summary)
    vevent.add("dtstart", dl.due_at)
    vevent.add("dtend", dl.due_at + timedelta(hours=1))
    vevent.add("uid", f"deadline-{dl.chat_id}-{dl.source_message_id or uuid.uuid4()}@orel-edu")
    vevent.add("categories", "Дедлайн")
    if dl.raw_quote:
        vevent.add("description", dl.raw_quote)

    for lead in (timedelta(hours=24), timedelta(hours=1)):
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", f"Напоминание: {summary}")
        alarm.add("trigger", -lead)
        vevent.add_component(alarm)

    return vevent

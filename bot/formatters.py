"""Форматирование ответов бота (HTML parse_mode).

Чистые функции list[ScheduleEvent]/list[Deadline] -> str. Без сети и БД,
легко тестируются. Конкретный визуальный формат ПРОВИЗОРНЫЙ — согласовать UX.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from shared.models import Deadline, ScheduleEvent

_WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_MSK = ZoneInfo("Europe/Moscow")


def _msk(dt: datetime) -> datetime:
    return dt.astimezone(_MSK)


def _fmt_time(dt: datetime) -> str:
    return _msk(dt).strftime("%H:%M")


def _fmt_event(ev: ScheduleEvent) -> str:
    parts = [f"<b>{_fmt_time(ev.starts_at)}–{_fmt_time(ev.ends_at)}</b> {escape(ev.discipline_name)}"]
    if ev.kind:
        parts.append(f"({escape(ev.kind)})")
    line = " ".join(parts)
    extra = []
    if ev.room:
        extra.append(f"ауд. {escape(ev.room)}")
    if ev.teacher:
        extra.append(escape(ev.teacher))
    if ev.online_link:
        extra.append(f'<a href="{escape(ev.online_link)}">ссылка</a>')
    if extra:
        line += "\n    " + " · ".join(extra)
    return line


def format_day(events: list[ScheduleEvent], *, title: str = "Сегодня") -> str:
    if not events:
        return f"<b>{escape(title)}</b>\nПар нет 🎉"
    events = sorted(events, key=lambda e: e.starts_at)
    body = "\n".join(_fmt_event(e) for e in events)
    return f"<b>{escape(title)}</b>\n{body}"


def format_week(events: list[ScheduleEvent]) -> str:
    if not events:
        return "<b>Неделя</b>\nПар нет 🎉"
    events = sorted(events, key=lambda e: e.starts_at)
    blocks: list[str] = []
    current_day: tuple[int, int, int] | None = None
    day_lines: list[str] = []
    for e in events:
        key = (e.starts_at.year, e.starts_at.month, e.starts_at.day)
        if key != current_day:
            if day_lines:
                blocks.append("\n".join(day_lines))
            msk_start = _msk(e.starts_at)
            wd = _WEEKDAYS_RU[msk_start.weekday()]
            day_lines = [f"\n<b>{wd}, {msk_start.strftime('%d.%m')}</b>"]
            current_day = key
        day_lines.append(_fmt_event(e))
    if day_lines:
        blocks.append("\n".join(day_lines))
    return "<b>Неделя</b>\n" + "\n".join(blocks)


def _fmt_deadline(d: Deadline) -> str:
    name = escape(d.discipline_name) if d.discipline_name else "—"
    work = f" · {escape(d.work_type)}" if d.work_type else ""
    when = _msk(d.due_at).strftime("%d.%m %H:%M") if d.due_at else "срок не указан"
    return f"📌 <b>{name}</b>{work} — {when}"


def format_discipline(
    name: str, events: list[ScheduleEvent], deadlines: list[Deadline]
) -> str:
    head = f"<b>{escape(name)}</b>"
    sched = format_day(sorted(events, key=lambda e: e.starts_at), title="Расписание") if events else "Расписание: нет ближайших пар"
    dl = "\n".join(_fmt_deadline(d) for d in deadlines) if deadlines else "Дедлайнов нет"
    return f"{head}\n\n{sched}\n\n<b>Дедлайны</b>\n{dl}"


def format_credits(events: list[ScheduleEvent], deadlines: list[Deadline]) -> str:
    """Зачёты/экзамены отдельным списком.

    TODO[contract]: db API не отдаёт control_form дисциплин напрямую. Сейчас
    фильтруем по kind пары и work_type дедлайна. Уточнить источник истины.
    """
    if not events and not deadlines:
        return "<b>Зачёты и экзамены</b>\nПока ничего не запланировано."
    lines = ["<b>Зачёты и экзамены</b>"]
    for e in sorted(events, key=lambda e: e.starts_at):
        lines.append(f"🎓 {escape(e.discipline_name)} — {_msk(e.starts_at).strftime('%d.%m %H:%M')}"
                     + (f" ({escape(e.kind)})" if e.kind else ""))
    for d in deadlines:
        lines.append(_fmt_deadline(d))
    return "\n".join(lines)

"""ИИ-чат по данным группы (CONTRACT.md §6).

Строит контекст из дедлайнов, расписания и истории сообщений (если уже есть)
и отвечает на вопрос студента через GigaChat.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from shared.models import Deadline, ScheduleEvent
from .llm import LLMClient

_TZ = ZoneInfo("Europe/Moscow")

_SYSTEM = """Ты помощник студенческой группы РАНХиГС «Единая учебная среда».
Тебе передан контекст: расписание занятий, список дедлайнов и (при наличии) история сообщений чата.
Отвечай кратко и по делу на русском языке, используя только предоставленный контекст.
Если информации недостаточно — честно скажи об этом. Не придумывай данные."""


def _fmt_deadline(d: Deadline) -> str:
    due = d.due_at.astimezone(_TZ).strftime("%d.%m %H:%M") if d.due_at else "срок не указан"
    parts = [f"• {d.discipline_name or '—'}"]
    if d.work_type:
        parts.append(f"({d.work_type})")
    parts.append(f"— {due}")
    if d.raw_quote:
        parts.append(f'[«{d.raw_quote[:80]}»]')
    return " ".join(parts)


def _fmt_event(e: ScheduleEvent) -> str:
    start = e.starts_at.astimezone(_TZ).strftime("%d.%m %H:%M")
    end = e.ends_at.astimezone(_TZ).strftime("%H:%M")
    room = f", {e.room}" if e.room else ""
    teacher = f", {e.teacher}" if e.teacher else ""
    kind = f" ({e.kind})" if e.kind else ""
    return f"• {start}–{end} {e.discipline_name}{kind}{room}{teacher}"


def _fmt_message(row: dict) -> str:
    who = row.get("full_name") or row.get("username") or "Участник"
    when = ""
    if row.get("sent_at"):
        try:
            dt = datetime.fromisoformat(row["sent_at"]).astimezone(_TZ)
            when = dt.strftime("%d.%m %H:%M") + " "
        except ValueError:
            pass
    return f"[{when}{who}]: {row['text']}"


def answer_question(
    question: str,
    client: LLMClient,
    *,
    deadlines: list[Deadline] | None = None,
    schedule: list[ScheduleEvent] | None = None,
    group_messages: list[dict] | None = None,
) -> str:
    """Ответить на вопрос студента, используя доступный контекст из БД."""
    sections: list[str] = []

    if deadlines:
        lines = [_fmt_deadline(d) for d in deadlines]
        sections.append("=== Дедлайны группы ===\n" + "\n".join(lines))
    else:
        sections.append("=== Дедлайны группы ===\nДедлайны не найдены.")

    if schedule:
        lines = [_fmt_event(e) for e in schedule]
        sections.append("=== Расписание (ближайшие 7 дней) ===\n" + "\n".join(lines))
    else:
        sections.append("=== Расписание ===\nРасписание не найдено (портал не привязан).")

    if group_messages:
        lines = [_fmt_message(m) for m in group_messages[-100:]]
        sections.append("=== История сообщений чата (последние) ===\n" + "\n".join(lines))

    context = "\n\n".join(sections)
    user_prompt = f"{context}\n\n=== Вопрос студента ===\n{question}"

    return client.complete(_SYSTEM, user_prompt)

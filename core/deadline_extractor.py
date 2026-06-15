"""ИИ-извлечение дедлайнов из сообщений чата (CONTRACT.md §6).

`extract_deadline(text, client, today)` отдаёт `DeadlineExtraction` — структуру,
которую вызывающая сторона (бот, `bot.mappers.extraction_to_deadline`) превращает
в `shared.models.Deadline`. Здесь — только распознавание, без записи в БД.

Относительные даты («к пятнице», «через неделю») разрешаются относительно `today`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.llm import LLMClient

MSK = ZoneInfo("Europe/Moscow")

_SYSTEM_PROMPT = (
    "Ты — извлекатель учебных дедлайнов из сообщений студенческого чата. "
    "Верни СТРОГО один JSON-объект без пояснений и markdown со схемой:\n"
    "{\n"
    '  "is_deadline": bool,            // это сообщение о дедлайне/задании?\n'
    '  "discipline_name": str|null,    // название дисциплины, если есть\n'
    '  "work_type": str|null,          // "ДЗ"|"реферат"|"презентация"|"зачёт"|...\n'
    '  "due_at": str|null,             // ISO 8601 дата-время дедлайна или null\n'
    '  "raw_quote": str|null,          // короткая цитата-первоисточник\n'
    '  "confidence": float             // 0..1 уверенность\n'
    "}\n"
    "Относительные сроки считай от переданной сегодняшней даты. "
    "Если это не дедлайн — is_deadline=false и confidence низкий."
)


@dataclass(slots=True)
class DeadlineExtraction:
    """Результат ИИ-распознавания. Маппинг в `Deadline` — на стороне бота."""

    is_deadline: bool = False
    discipline_name: str | None = None
    work_type: str | None = None
    due_at: datetime | None = None
    raw_quote: str | None = None
    confidence: float = 0.0

    def is_actionable(self) -> bool:
        """Стоит ли вообще сохранять: это дедлайн и есть за что зацепиться."""
        return self.is_deadline and (self.due_at is not None or bool(self.work_type))


def extract_deadline(message_text: str, client: LLMClient, today: date) -> DeadlineExtraction:
    """Извлечь дедлайн из текста через LLM. Никогда не бросает на «грязный» ответ —
    при сбое парсинга возвращает не-actionable результат с confidence=0."""
    user_prompt = f"Сегодня: {today.isoformat()}\nСообщение:\n{message_text}"
    try:
        raw = client.complete(_SYSTEM_PROMPT, user_prompt)
    except Exception:  # noqa: BLE001 — LLM не должен ронять приём сообщений
        return DeadlineExtraction(is_deadline=False, raw_quote=message_text, confidence=0.0)

    data = _parse_json(raw)
    if not isinstance(data, dict):
        return DeadlineExtraction(is_deadline=False, raw_quote=message_text, confidence=0.0)

    return DeadlineExtraction(
        is_deadline=bool(data.get("is_deadline", False)),
        discipline_name=_str_or_none(data.get("discipline_name")),
        work_type=_str_or_none(data.get("work_type")),
        due_at=_parse_due(data.get("due_at")),
        raw_quote=_str_or_none(data.get("raw_quote")) or message_text,
        confidence=_clamp(data.get("confidence", 0.0)),
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> object:
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Модель могла обернуть JSON в ```json ... ``` или текст — вырежем объект.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _str_or_none(value: object) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _parse_due(value: object) -> datetime | None:
    text = _str_or_none(value)
    if text is None:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=MSK)


def _clamp(value: object) -> float:
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, conf))

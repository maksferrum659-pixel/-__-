"""Маппинг результата ИИ-ядра в модель БД.

`DeadlineExtraction` (выход `core.extract_deadline`) -> `Deadline` (shared.models).
Маппинг — ответственность вызывающей стороны (бота), см. CONTRACT.md §5.
Чистая функция без побочных эффектов — отдельно, чтобы покрыть юнит-тестом.
"""
from __future__ import annotations

from typing import Any

from shared.models import Deadline


def extraction_to_deadline(
    extraction: Any,  # core.deadline_extractor.DeadlineExtraction
    *,
    chat_id: int,
    source_message_id: int,
    confidence_threshold: float,
) -> Deadline | None:
    """Превратить извлечение в Deadline или вернуть None, если сохранять не нужно.

    None, если извлечение не actionable ИЛИ confidence ниже порога.

    TODO[contract]: точные имена полей DeadlineExtraction подтвердить по
    core/deadline_extractor.py (модуль пока недоступен в ветке). Сейчас берём
    через getattr с дефолтом None — поправить на прямой доступ после сверки.
    """
    if not extraction.is_actionable():
        return None
    if extraction.confidence < confidence_threshold:
        return None

    return Deadline(
        chat_id=chat_id,
        discipline_name=getattr(extraction, "discipline_name", None),
        work_type=getattr(extraction, "work_type", None),
        due_at=getattr(extraction, "due_at", None),
        raw_quote=getattr(extraction, "raw_quote", None),
        confidence=extraction.confidence,
        source_message_id=source_message_id,
    )

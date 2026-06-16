"""Хендлеры группового бота (мониторинг чата → дедлайны через GigaChat AI).

Бот добавляется в учебный групповой чат и молча сохраняет дедлайны.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import Message

import db
from core.deadline_extractor import extract_deadline
from core.llm import GigaChatClient

from .config import Settings
from .mappers import extraction_to_deadline

logger = logging.getLogger(__name__)
router = Router(name="group")

_llm = GigaChatClient()


def _tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.timezone)


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def on_group_message(message: Message, settings: Settings) -> None:
    extraction = extract_deadline(message.text, _llm, datetime.now(_tz(settings)).date())
    deadline = extraction_to_deadline(
        extraction,
        chat_id=message.chat.id,
        source_message_id=message.message_id,
        confidence_threshold=settings.confidence_threshold,
    )
    if deadline is None:
        return
    db.upsert_deadline(deadline)
    logger.info("Сохранён дедлайн из чата %s (msg=%s)", message.chat.id, message.message_id)

"""Хендлеры группового бота (@informationRRbot): мониторинг чата.

Бот добавлен в учебный групповой чат (privacy выключен) и молча:
1. привязывает участников чата к этому чату (`db.save_group_chat_id`) — так
   личный бот узнаёт, по какому `chat_id` искать дедлайны для конкретного студента;
2. извлекает дедлайны из текста через GigaChat (`core.extract_deadline`) и
   сохраняет их (`db.upsert_deadline`).
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
    if message.from_user:
        try:
            db.save_group_chat_id(message.from_user.id, message.chat.id)
        except Exception:  # noqa: BLE001 — миграция 006 может быть ещё не применена
            logger.warning("Не удалось сохранить group_chat_id (chat=%s)", message.chat.id)

    extraction = extract_deadline(message.text, _llm, datetime.now(_tz(settings)).date())
    deadline = extraction_to_deadline(
        extraction,
        chat_id=message.chat.id,
        source_message_id=message.message_id,
        confidence_threshold=settings.confidence_threshold,
    )
    if deadline is None:
        return  # не дедлайн / низкая уверенность — молчим
    db.upsert_deadline(deadline)  # дедуп по (chat_id, source_message_id)
    logger.info("Сохранён дедлайн из чата %s (msg=%s)", message.chat.id, message.message_id)

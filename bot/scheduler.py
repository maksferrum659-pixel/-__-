"""Периодические задачи (APScheduler).

1) Синк расписания: db.list_users_with_token() → decrypt_token →
   parser.fetch_schedule() → db.upsert_schedule_events(). Связка parser↔db живёт ЗДЕСЬ.
2) Напоминания: по db.list_deadlines и ближайшим парам — уведомления пользователю.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db
from core.security import decrypt_token
import parser

from .config import Settings

logger = logging.getLogger(__name__)


async def sync_schedules(settings: Settings) -> None:
    """Подтянуть свежее расписание для всех привязавших портал пользователей."""
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    since, until = today, today + timedelta(days=90)
    for telegram_id in db.list_users_with_token():
        enc = db.get_portal_token(telegram_id)
        if not enc:
            continue
        try:
            token = decrypt_token(enc)
            events = parser.fetch_schedule(token, since, until)
            saved = db.upsert_schedule_events(telegram_id, events)
            logger.info("Синк расписания telegram_id=%s: %s событий", telegram_id, saved)
        except Exception:  # noqa: BLE001 — один пользователь не должен ронять весь цикл
            logger.exception("Сбой синка расписания для telegram_id=%s", telegram_id)


async def send_reminders(bot: Bot, settings: Settings) -> None:
    """Разослать напоминания о приближающихся дедлайнах.

    TODO[contract/UX]: горизонт «ближайших», дедуп уже отправленных напоминаний
    и аудитория (кому в группе) контрактом не зафиксированы. Сейчас — простой
    проход по открытым дедлайнам в окне reminder_lead_times. Нужна таблица
    «отправленных», иначе будут повторы (db API её пока не предоставляет — вопрос к §6).
    """
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    # Окно: ближайший из lead-time'ов задаёт горизонт.
    horizon = now + max(settings.reminder_lead_times)
    # Перебор активных чатов недоступен через db API напрямую — см. TODO выше.
    logger.debug("send_reminders tick @ %s (горизонт %s)", now.isoformat(), horizon.isoformat())


def setup_scheduler(bot: Bot, settings: Settings) -> AsyncIOScheduler:
    """Создать и сконфигурировать планировщик (не запускает — вызови .start())."""
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        sync_schedules,
        "interval",
        hours=settings.schedule_sync_interval_hours,
        args=[settings],
        id="sync_schedules",
        next_run_time=datetime.now(ZoneInfo(settings.timezone)),  # один синк сразу на старте
    )
    scheduler.add_job(
        send_reminders,
        "interval",
        minutes=settings.reminder_scan_interval_minutes,
        args=[bot, settings],
        id="send_reminders",
    )
    return scheduler

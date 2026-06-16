"""Точка входа: два бота — личный (BOT_TOKEN) и групповой (GROUP_BOT_TOKEN)."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from . import handlers_personal, handlers_group
from .config import load_settings
from .scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_BOT_DEFAULTS = DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True)


async def _run_personal(settings) -> None:
    """Личный бот: команды расписания, FSM привязки портала, планировщик."""
    bot = Bot(token=settings.bot_token, default=_BOT_DEFAULTS)
    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    dp.include_router(handlers_personal.router)

    scheduler = setup_scheduler(bot, settings)
    scheduler.start()
    logger.info("Личный бот запущен, планировщик активен (синк раз в %d ч)",
                settings.schedule_sync_interval_hours)
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


async def _run_group(settings) -> None:
    """Групповой бот: слушает чат, сохраняет дедлайны через GigaChat AI."""
    bot = Bot(token=settings.group_bot_token, default=_BOT_DEFAULTS)
    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    dp.include_router(handlers_group.router)

    logger.info("Групповой бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


async def main() -> None:
    settings = load_settings()
    await asyncio.gather(_run_personal(settings), _run_group(settings))


if __name__ == "__main__":
    asyncio.run(main())

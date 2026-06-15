"""Точка входа бота: конфиг → Bot/Dispatcher → хендлеры → планировщик → polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from . import handlers
from .config import load_settings
from .scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = load_settings()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dp = Dispatcher(storage=MemoryStorage())
    # settings прокидываем в хендлеры/джобы через workflow data (DI aiogram).
    dp["settings"] = settings

    handlers.register(dp)

    scheduler = setup_scheduler(bot, settings)
    scheduler.start()
    logger.info("Планировщик запущен (синк раз в %d ч)", settings.schedule_sync_interval_hours)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

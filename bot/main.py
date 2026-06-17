"""Точка входа: два независимых бота в одном процессе.

- Личный (@TimetableRRBot, BOT_TOKEN) — команды, FSM, ИИ-чат, планировщик синка.
- Групповой (@informationRRbot, GROUP_BOT_TOKEN) — слушает учебный чат, извлекает дедлайны.

Боты независимы (разные токены, разные роутеры, разные Dispatcher) и работают
конкурентно через `asyncio.gather`; падение одного не останавливает другой.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from . import handlers_group, handlers_personal
from .config import Settings, load_settings
from .scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_BOT_DEFAULTS = DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True)


def _make_session() -> AiohttpSession:
    # Telegram заблокирован напрямую — ходим через SOCKS5 (VPN), для обоих ботов.
    return AiohttpSession(proxy="socks5://127.0.0.1:10808")


async def _run_personal(settings: Settings) -> None:
    bot = Bot(token=settings.bot_token, session=_make_session(), default=_BOT_DEFAULTS)
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


async def _run_group(settings: Settings) -> None:
    bot = Bot(token=settings.group_bot_token, session=_make_session(), default=_BOT_DEFAULTS)
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

"""Хендлеры личного бота (личная переписка студента с ботом).

Команды: /start, /link (FSM привязки портала), /today, /week, /discipline, /credits.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import db
from core.security import encrypt_token
import parser

from .config import Settings
from .formatters import format_credits, format_day, format_discipline, format_week

logger = logging.getLogger(__name__)
router = Router(name="personal")


class PortalLink(StatesGroup):
    """FSM привязки портала в личке."""
    waiting_credentials = State()


def _tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.timezone)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    db.get_or_create_user(message.from_user.id)
    await message.answer(
        "Привет! Я свожу твоё расписание и дедлайны в одно место.\n\n"
        "Чтобы подтянуть расписание — привяжи портал командой /link "
        "(логин и пароль присылай только мне в личку).\n\n"
        "Команды: /today /week /discipline &lt;название&gt; /credits"
    )


@router.message(Command("link"), F.chat.type == "private")
async def cmd_link(message: Message, state: FSMContext) -> None:
    await state.set_state(PortalLink.waiting_credentials)
    await message.answer(
        "Пришли логин и пароль от портала одним сообщением через пробел:\n"
        "<code>логин пароль</code>\n\n"
        "Я зашифрую токен и сразу удалю твоё сообщение. Пароль нигде не сохраняю."
    )


@router.message(PortalLink.waiting_credentials, F.chat.type == "private", F.text)
async def on_credentials(message: Message, state: FSMContext) -> None:
    await state.clear()
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        logger.warning("Не удалось удалить сообщение с учёткой (chat=%s)", message.chat.id)

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Нужны логин и пароль через пробел. Повтори /link.")
        return
    login, password = parts[0], " ".join(parts[1:])

    try:
        token = parser.authenticate(login, password)
    except Exception:  # noqa: BLE001
        logger.exception("Аутентификация на портале не удалась (telegram_id=%s)", message.from_user.id)
        await message.answer("Не вышло войти на портал. Проверь логин/пароль и повтори /link.")
        return
    finally:
        del password

    db.save_portal_token(message.from_user.id, encrypt_token(token))
    await message.answer("Готово ✅ Портал привязан. Скоро подтяну расписание.")


@router.message(Command("today"))
async def cmd_today(message: Message, settings: Settings) -> None:
    tz = _tz(settings)
    now = datetime.now(tz)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    until = since + timedelta(days=1)
    events = db.get_schedule(message.from_user.id, since, until)
    await message.answer(format_day(events, title="Сегодня"))


@router.message(Command("week"))
async def cmd_week(message: Message, settings: Settings) -> None:
    tz = _tz(settings)
    now = datetime.now(tz)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    until = since + timedelta(days=7)
    events = db.get_schedule(message.from_user.id, since, until)
    await message.answer(format_week(events))


@router.message(Command("discipline"))
async def cmd_discipline(message: Message, command: CommandObject, settings: Settings) -> None:
    name = (command.args or "").strip()
    if not name:
        await message.answer("Укажи дисциплину: <code>/discipline Матанализ</code>")
        return
    tz = _tz(settings)
    now = datetime.now(tz)
    events = db.get_schedule(message.from_user.id, now, now + timedelta(days=30))
    events = [e for e in events if name.lower() in e.discipline_name.lower()]
    deadlines = db.list_deadlines(message.chat.id, only_open=True) if message.chat.type != "private" else []
    deadlines = [d for d in deadlines if d.discipline_name and name.lower() in d.discipline_name.lower()]
    await message.answer(format_discipline(name, events, deadlines))


@router.message(Command("credits"))
async def cmd_credits(message: Message, settings: Settings) -> None:
    tz = _tz(settings)
    now = datetime.now(tz)
    events = db.get_schedule(message.from_user.id, now, now + timedelta(days=120))
    control = {"зачёт", "зачет", "экзамен"}
    events = [e for e in events if e.kind and e.kind.lower() in control]
    deadlines = db.list_deadlines(message.chat.id, only_open=True) if message.chat.type != "private" else []
    deadlines = [d for d in deadlines if d.work_type and d.work_type.lower() in control]
    await message.answer(format_credits(events, deadlines))

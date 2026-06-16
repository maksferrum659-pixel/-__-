"""Хендлеры команд и сообщений чата (aiogram 3.x).

Данные берём из `db` (не из портала напрямую). Дедлайны извлекаем через `core`.
Привязка портала идёт через `parser` + `core.security`. Пароль НЕ логируем и НЕ храним.
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
from core.deadline_extractor import extract_deadline
from core import ai_chat
from core.llm import GigaChatClient
from core.security import encrypt_token
import parser

from .config import Settings
from .formatters import format_credits, format_day, format_discipline, format_week
from .mappers import extraction_to_deadline

logger = logging.getLogger(__name__)
router = Router(name="bot")

# Один экземпляр LLM-клиента на процесс (см. core.llm.GigaChatClient).
_llm = GigaChatClient()


class PortalLink(StatesGroup):
    """FSM привязки портала в личке."""
    waiting_credentials = State()


def _tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.timezone)


# --------------------------------------------------------------------------- #
# Команды
# --------------------------------------------------------------------------- #
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
    # Удаляем сообщение с паролем как можно раньше; не логируем содержимое.
    try:
        await message.delete()
    except Exception:  # noqa: BLE001 — у бота может не быть прав на удаление
        logger.warning("Не удалось удалить сообщение с учёткой (chat=%s)", message.chat.id)

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Нужны логин и пароль через пробел. Повтори /link.")
        return
    login, password = parts[0], " ".join(parts[1:])

    try:
        token = parser.authenticate(login, password)  # parser → портал
    except Exception:  # noqa: BLE001
        logger.exception("Аутентификация на портале не удалась (telegram_id=%s)", message.from_user.id)
        await message.answer("Не вышло войти на портал. Проверь логин/пароль и повтори /link.")
        return
    finally:
        del password  # на всякий случай не держим пароль в кадре дольше нужного

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
    # Дедлайны групповые (по chat_id). В группе берём текущий чат.
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


# --------------------------------------------------------------------------- #
# ИИ-чат: /ask <вопрос>
# --------------------------------------------------------------------------- #
@router.message(Command("ask"))
async def cmd_ask(message: Message, command: CommandObject, settings: Settings) -> None:
    question = (command.args or "").strip()
    if not question:
        await message.answer("Задай вопрос: <code>/ask что задали по праву?</code>")
        return

    tz = _tz(settings)
    now = datetime.now(tz)

    # В группе запоминаем привязку chat_id → user, чтобы /ask работал и в личке
    if message.chat.type in ("group", "supergroup"):
        chat_id: int | None = message.chat.id
        db.save_group_chat_id(message.from_user.id, chat_id)
    else:
        chat_id = db.get_group_chat_id(message.from_user.id)

    deadlines = db.list_deadlines(chat_id, only_open=True) if chat_id else []
    group_messages = db.get_group_messages(chat_id) if chat_id else []
    schedule = db.get_schedule(message.from_user.id, now, now + timedelta(days=7))

    thinking = await message.answer("Думаю…")

    try:
        answer = ai_chat.answer_question(
            question,
            _llm,
            deadlines=deadlines,
            schedule=schedule,
            group_messages=group_messages,
        )
    except Exception:
        logger.exception("Ошибка ИИ-чата (chat=%s)", message.chat.id)
        await thinking.delete()
        await message.answer("Не удалось получить ответ от ИИ. Попробуй позже.")
        return

    await thinking.delete()
    await message.answer(answer)


# --------------------------------------------------------------------------- #
# Приём сообщений группового чата → дедлайны (ИИ-поток)
# --------------------------------------------------------------------------- #
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
        return  # не дедлайн / низкая уверенность — молчим
    db.upsert_deadline(deadline)  # дедуп по (chat_id, source_message_id)
    logger.info("Сохранён дедлайн из чата %s (msg=%s)", message.chat.id, message.message_id)


def register(router_root) -> None:
    """Подключить этот роутер к диспетчеру/корневому роутеру."""
    router_root.include_router(router)

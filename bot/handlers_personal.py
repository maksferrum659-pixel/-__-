"""Хендлеры личного бота (@TimetableRRBot): команды, FSM, кнопки, ИИ-чат.

Данные берём из `db` (не из портала напрямую). Привязка портала идёт через
`parser` + `core.security`. Пароль НЕ логируем и НЕ храним.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

import db
from core import ai_chat
from core.llm import GigaChatClient
from core.security import encrypt_token
import parser

from .config import Settings
from .formatters import format_credits, format_day, format_discipline, format_week

logger = logging.getLogger(__name__)
router = Router(name="personal")

# Один экземпляр LLM-клиента на процесс (см. core.llm.GigaChatClient).
_llm = GigaChatClient()


class PortalLink(StatesGroup):
    """FSM привязки портала в личке."""
    waiting_credentials = State()


class YandexEmail(StatesGroup):
    """FSM сохранения Яндекс-почты для календаря."""
    waiting_email = State()


class DisciplineSearch(StatesGroup):
    """FSM поиска по предмету через кнопку."""
    waiting_name = State()


class AskQuestion(StatesGroup):
    """FSM вопроса к ИИ по данным группы."""
    waiting_question = State()


GROUPS = ["Группа 1", "Группа 2"]


def _tz(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def _commands_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="📆 Неделя")],
            [KeyboardButton(text="🎓 Зачёты"), KeyboardButton(text="🔍 По предмету")],
            [KeyboardButton(text="📱 Мини апп"), KeyboardButton(text="💬 Задать вопрос")],
            [KeyboardButton(text="🔄 Заново заполнить данные")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _group_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👥 {g}", callback_data=f"group:{g}")] for g in GROUPS
    ])


def _main_keyboard(current_group: str | None = None) -> InlineKeyboardMarkup:
    group_label = f"👥 Группа: {current_group}" if current_group else "👥 Выбрать группу"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=group_label, callback_data="do_group")],
        [InlineKeyboardButton(text="🔗 Привязать портал РАНХИГС", callback_data="do_link")],
        [InlineKeyboardButton(text="📧 Указать Яндекс-почту", callback_data="do_email")],
        [InlineKeyboardButton(text="📱 Мини-приложение (скоро)", callback_data="miniapp_soon")],
    ])


# --------------------------------------------------------------------------- #
# Команды
# --------------------------------------------------------------------------- #
@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    db.get_or_create_user(message.from_user.id)
    name = message.from_user.first_name or "студент"
    current_group = db.get_academic_group(message.from_user.id)
    await message.answer(
        f"Привет, {name}! 👋\n\n"
        "Я <b>помогаю студентам РАНХИГС</b> не терять расписание и дедлайны.\n\n"
        "<b>Что я умею:</b>\n"
        "📅 Расписание на сегодня и неделю\n"
        "🔍 Поиск по предмету — пары и дедлайны\n"
        "🎓 Зачёты и экзамены\n"
        "🤖 Слушаю групповой чат и сам нахожу дедлайны\n\n"
        "<b>Чтобы начать, нужно:</b>\n"
        "1️⃣ Выбрать свою группу\n"
        "2️⃣ Привязать логин/пароль от портала rr-edu.ranepa.ru\n"
        "3️⃣ Указать Яндекс-почту для подписки на календарь\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=_commands_keyboard(),
    )
    await message.answer("Настройки:", reply_markup=_main_keyboard(current_group))
    if not current_group:
        await message.answer("Для начала выбери свою группу:", reply_markup=_group_keyboard())


@router.callback_query(lambda c: c.data == "do_link")
async def on_cb_link(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(PortalLink.waiting_credentials)
    await callback.message.answer(
        "Пришли логин и пароль от портала одним сообщением через пробел:\n"
        "<code>логин пароль</code>\n\n"
        "Я зашифрую токен и сразу удалю твоё сообщение. Пароль нигде не сохраняю."
    )


@router.callback_query(lambda c: c.data == "do_email")
async def on_cb_email(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(YandexEmail.waiting_email)
    await callback.message.answer(
        "Пришли свой Яндекс-адрес, чтобы я мог отправить ссылку на подписку календаря:\n"
        "<code>example@yandex.ru</code>"
    )


@router.callback_query(lambda c: c.data == "miniapp_soon")
async def on_cb_miniapp(callback: CallbackQuery, settings: Settings) -> None:
    if settings.mini_app_url:
        await callback.answer()
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📱 Открыть расписание",
                web_app=WebAppInfo(url=settings.mini_app_url),
            )
        ]])
        await callback.message.answer("Нажми кнопку, чтобы открыть расписание:", reply_markup=kb)
    else:
        await callback.answer("Мини-приложение в разработке — скоро будет! 🚀", show_alert=True)


@router.callback_query(lambda c: c.data == "do_group")
async def on_cb_do_group(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Выбери свою группу:", reply_markup=_group_keyboard())


@router.callback_query(lambda c: c.data and c.data.startswith("group:"))
async def on_cb_group_selected(callback: CallbackQuery) -> None:
    group = callback.data.split(":", 1)[1]
    if group not in GROUPS:
        await callback.answer("Неизвестная группа.", show_alert=True)
        return
    db.save_academic_group(callback.from_user.id, group)
    await callback.answer(f"✅ Сохранено: {group}", show_alert=False)
    await callback.message.edit_text(
        f"✅ Твоя группа: <b>{group}</b>\n\nТеперь привяжи портал — нажми «Настройки» (/start)."
    )


@router.message(YandexEmail.waiting_email, F.chat.type == "private", F.text)
async def on_yandex_email(message: Message, state: FSMContext) -> None:
    await state.clear()
    email = (message.text or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        await message.answer("Не похоже на почту. Попробуй ещё раз — нажми «Указать Яндекс-почту».")
        return
    db.save_yandex_email(message.from_user.id, email)
    await message.answer(
        f"✅ Почта <code>{email}</code> сохранена.\n"
        "Когда подключим календарь — пришлю ссылку на подписку."
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
async def on_credentials(message: Message, state: FSMContext, settings: Settings) -> None:
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
    await message.answer("Готово ✅ Портал привязан. Подтягиваю расписание…")
    from .scheduler import sync_schedules
    asyncio.create_task(sync_schedules(settings))


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
    # Дедлайны групповые — берём чат, привязанный к пользователю групповым ботом.
    chat_id = db.get_group_chat_id(message.from_user.id) if message.chat.type == "private" else message.chat.id
    deadlines = db.list_deadlines(chat_id, only_open=True) if chat_id else []
    deadlines = [d for d in deadlines if d.discipline_name and name.lower() in d.discipline_name.lower()]
    await message.answer(format_discipline(name, events, deadlines))


@router.message(Command("credits"))
async def cmd_credits(message: Message, settings: Settings) -> None:
    tz = _tz(settings)
    now = datetime.now(tz)
    events = db.get_schedule(message.from_user.id, now, now + timedelta(days=120))
    control = {"зачёт", "зачет", "экзамен", "зачет с оценкой", "зачёт с оценкой", "дифференцированный зачёт", "дифференцированный зачет"}
    events = [e for e in events if e.kind and any(k in e.kind.lower() for k in control)]
    chat_id = db.get_group_chat_id(message.from_user.id) if message.chat.type == "private" else message.chat.id
    deadlines = db.list_deadlines(chat_id, only_open=True) if chat_id else []
    deadlines = [d for d in deadlines if d.work_type and d.work_type.lower() in control]
    await message.answer(format_credits(events, deadlines))


# --------------------------------------------------------------------------- #
# Кнопки нижней клавиатуры (личка)
# --------------------------------------------------------------------------- #
@router.message(F.text == "📅 Сегодня", F.chat.type == "private")
async def btn_today(message: Message, settings: Settings) -> None:
    await cmd_today(message, settings)


@router.message(F.text == "📆 Неделя", F.chat.type == "private")
async def btn_week(message: Message, settings: Settings) -> None:
    await cmd_week(message, settings)


@router.message(F.text == "🎓 Зачёты", F.chat.type == "private")
async def btn_credits(message: Message, settings: Settings) -> None:
    await cmd_credits(message, settings)


@router.message(F.text == "🔍 По предмету", F.chat.type == "private")
async def btn_discipline(message: Message, state: FSMContext) -> None:
    await state.set_state(DisciplineSearch.waiting_name)
    await message.answer("Напиши название предмета (или часть):")


@router.message(DisciplineSearch.waiting_name, F.chat.type == "private", F.text)
async def on_discipline_name(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    name = (message.text or "").strip()
    tz = _tz(settings)
    now = datetime.now(tz)
    events = db.get_schedule(message.from_user.id, now, now + timedelta(days=30))
    events = [e for e in events if name.lower() in e.discipline_name.lower()]
    chat_id = db.get_group_chat_id(message.from_user.id)
    deadlines = db.list_deadlines(chat_id, only_open=True) if chat_id else []
    deadlines = [d for d in deadlines if d.discipline_name and name.lower() in d.discipline_name.lower()]
    await message.answer(format_discipline(name, events, deadlines))


@router.message(F.text == "📱 Мини апп", F.chat.type == "private")
async def btn_miniapp(message: Message, settings: Settings) -> None:
    if settings.mini_app_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="📱 Открыть расписание",
                web_app=WebAppInfo(url=settings.mini_app_url),
            )
        ]])
        await message.answer("Нажми кнопку:", reply_markup=kb)
    else:
        await message.answer("Мини-приложение скоро будет готово! 🚀")


@router.message(F.text == "🔄 Заново заполнить данные", F.chat.type == "private")
async def btn_refill(message: Message) -> None:
    current_group = db.get_academic_group(message.from_user.id)
    await message.answer("Настройки:", reply_markup=_main_keyboard(current_group))
    if not current_group:
        await message.answer("Выбери свою группу:", reply_markup=_group_keyboard())


@router.message(F.text == "💬 Задать вопрос", F.chat.type == "private")
async def btn_ask(message: Message, state: FSMContext) -> None:
    await state.set_state(AskQuestion.waiting_question)
    await message.answer(
        "Напиши вопрос — отвечу на основе расписания и дедлайнов группы.\n\n"
        "Например: <i>«Что нужно сдать по психологии?»</i> или <i>«Когда следующий зачёт?»</i>"
    )


@router.message(AskQuestion.waiting_question, F.chat.type == "private", F.text)
async def on_ask_question(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    question = (message.text or "").strip()
    thinking = await message.answer("Думаю…")
    try:
        tz = _tz(settings)
        now = datetime.now(tz)
        chat_id = db.get_group_chat_id(message.from_user.id)
        deadlines = db.list_deadlines(chat_id, only_open=True) if chat_id else []
        schedule = db.get_schedule(message.from_user.id, now, now + timedelta(days=7))
        answer = ai_chat.answer_question(question, _llm, deadlines=deadlines, schedule=schedule)
    except Exception:
        logger.exception("Ошибка ИИ-чата (user=%s)", message.from_user.id)
        await thinking.delete()
        await message.answer("Не удалось получить ответ от ИИ. Попробуй позже.")
        return
    await thinking.delete()
    await message.answer(answer)

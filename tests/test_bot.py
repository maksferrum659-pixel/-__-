"""Тесты бота: чистые функции + хендлеры с замоканными db.* (без сети/БД).

Если общие модули (shared/core/db/parser) ещё не подложены в ветку — модуль
аккуратно скипается целиком (importorskip), а не падает на сборке.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

# Пререкизиты: контрактные модели и сам пакет бота должны импортироваться.
pytest.importorskip("shared.models")
pytest.importorskip("bot.handlers_personal")
pytest.importorskip("bot.handlers_group")

from shared.models import Deadline, ScheduleEvent  # noqa: E402
from bot import handlers_group, handlers_personal  # noqa: E402
from bot.config import Settings  # noqa: E402
from bot.mappers import extraction_to_deadline  # noqa: E402

MSK = ZoneInfo("Europe/Moscow")


def _settings(**over) -> Settings:
    base = dict(
        bot_token="x", group_bot_token="x", gigachat_credentials="x",
        fernet_key="x", supabase_url="x", supabase_service_key="x",
    )
    base.update(over)
    return Settings(**base)


def _fake_extraction(*, actionable=True, confidence=0.9, **fields):
    ns = SimpleNamespace(confidence=confidence, **fields)
    ns.is_actionable = lambda: actionable
    return ns


# --------------------------- маппинг DeadlineExtraction -> Deadline --------- #
def test_mapping_fills_deadline_fields():
    due = datetime(2026, 6, 20, 18, 0, tzinfo=MSK)
    ext = _fake_extraction(
        confidence=0.95, discipline_name="Матанализ", work_type="ДЗ",
        due_at=due, raw_quote="сдать дз к пятнице",
    )
    d = extraction_to_deadline(ext, chat_id=42, source_message_id=7, confidence_threshold=0.7)
    assert isinstance(d, Deadline)
    assert d.chat_id == 42 and d.source_message_id == 7
    assert d.discipline_name == "Матанализ" and d.work_type == "ДЗ"
    assert d.due_at == due and d.confidence == 0.95


def test_mapping_below_threshold_returns_none():
    ext = _fake_extraction(confidence=0.4, discipline_name="X")
    assert extraction_to_deadline(ext, chat_id=1, source_message_id=1, confidence_threshold=0.7) is None


def test_mapping_not_actionable_returns_none():
    ext = _fake_extraction(actionable=False, confidence=0.99)
    assert extraction_to_deadline(ext, chat_id=1, source_message_id=1, confidence_threshold=0.7) is None


# --------------------------- хендлеры с замоканными db ---------------------- #
def _msg(*, chat_type="private", chat_id=100, user_id=100, text=None, message_id=1):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type=chat_type),
        from_user=SimpleNamespace(id=user_id),
        text=text, message_id=message_id,
        answer=AsyncMock(), delete=AsyncMock(),
    )


def test_cmd_today_reads_db_and_answers(monkeypatch):
    ev = ScheduleEvent(
        external_id="e1", telegram_id=100, discipline_name="Физика",
        starts_at=datetime(2026, 6, 15, 9, 0, tzinfo=MSK),
        ends_at=datetime(2026, 6, 15, 10, 30, tzinfo=MSK),
    )
    fake_db = SimpleNamespace(get_schedule=lambda tid, since, until: [ev])
    monkeypatch.setattr(handlers_personal, "db", fake_db)
    msg = _msg()
    asyncio.run(handlers_personal.cmd_today(msg, _settings()))
    msg.answer.assert_awaited_once()
    assert "Физика" in msg.answer.call_args.args[0]


def test_group_message_links_user_and_saves_deadline(monkeypatch):
    captured = {}
    fake_db = SimpleNamespace(
        upsert_deadline=lambda d: captured.setdefault("d", d) or d,
        save_group_chat_id=lambda tid, cid: captured.setdefault("link", (tid, cid)),
    )
    monkeypatch.setattr(handlers_group, "db", fake_db)
    monkeypatch.setattr(
        handlers_group, "extract_deadline",
        lambda text, llm, today: _fake_extraction(
            confidence=0.9, discipline_name="История", work_type="реферат",
            due_at=None, raw_quote=text,
        ),
    )
    msg = _msg(chat_type="supergroup", chat_id=-555, user_id=777, message_id=12, text="реферат к среде")
    asyncio.run(handlers_group.on_group_message(msg, _settings()))
    assert captured["d"].chat_id == -555 and captured["d"].source_message_id == 12
    assert captured["link"] == (777, -555)


def test_group_message_skips_low_confidence(monkeypatch):
    fake_db = SimpleNamespace(
        upsert_deadline=AsyncMock(),  # не должен вызваться
        save_group_chat_id=lambda tid, cid: None,
    )
    monkeypatch.setattr(handlers_group, "db", fake_db)
    monkeypatch.setattr(
        handlers_group, "extract_deadline",
        lambda text, llm, today: _fake_extraction(confidence=0.2),
    )
    msg = _msg(chat_type="group", text="просто болтовня")
    asyncio.run(handlers_group.on_group_message(msg, _settings(confidence_threshold=0.7)))
    fake_db.upsert_deadline.assert_not_called()


def test_group_message_survives_missing_group_chat_id_column(monkeypatch):
    """Если миграция 006 не применена, save_group_chat_id падает — дедлайн всё равно сохраняется."""
    captured = {}

    def _boom(tid, cid):
        raise RuntimeError("column users.group_chat_id does not exist")

    fake_db = SimpleNamespace(
        upsert_deadline=lambda d: captured.setdefault("d", d) or d,
        save_group_chat_id=_boom,
    )
    monkeypatch.setattr(handlers_group, "db", fake_db)
    monkeypatch.setattr(
        handlers_group, "extract_deadline",
        lambda text, llm, today: _fake_extraction(
            confidence=0.9, discipline_name="История", work_type="реферат",
            due_at=None, raw_quote=text,
        ),
    )
    msg = _msg(chat_type="supergroup", chat_id=-555, message_id=12, text="реферат к среде")
    asyncio.run(handlers_group.on_group_message(msg, _settings()))
    assert captured["d"].chat_id == -555


def test_ask_question_survives_missing_group_chat_id_column(monkeypatch):
    """db.get_group_chat_id падает (нет колонки) — пользователь получает мягкую ошибку, не краш."""
    def _boom(tid):
        raise RuntimeError("column users.group_chat_id does not exist")

    fake_db = SimpleNamespace(get_group_chat_id=_boom)
    monkeypatch.setattr(handlers_personal, "db", fake_db)
    state = AsyncMock()
    msg = _msg(text="когда зачёт?")
    asyncio.run(handlers_personal.on_ask_question(msg, state, _settings()))
    state.clear.assert_awaited_once()
    assert "Не удалось получить ответ" in msg.answer.call_args.args[0]


def test_free_text_goes_to_ai_chat(monkeypatch):
    fake_db = SimpleNamespace(
        get_group_chat_id=lambda tid: None,
        list_deadlines=lambda cid, only_open=True: [],
        get_schedule=lambda tid, since, until: [],
    )
    monkeypatch.setattr(handlers_personal, "db", fake_db)
    monkeypatch.setattr(handlers_personal.ai_chat, "answer_question", lambda *a, **kw: "Ответ ИИ")
    msg = _msg(text="когда следующая физика?")
    asyncio.run(handlers_personal.on_free_text(msg, _settings()))
    assert msg.answer.call_args.args[0] == "Ответ ИИ"


def test_free_text_handler_registered_last():
    """on_free_text должен быть последним в роутере — иначе он перехватит команды/FSM-шаги."""
    handlers = handlers_personal.router.observers["message"].handlers
    assert handlers[-1].callback.__name__ == "on_free_text"


def test_cmd_calendar_sends_webcal_link(monkeypatch):
    fake_db = SimpleNamespace(get_or_create_ical_token=lambda tid: "abc123")
    monkeypatch.setattr(handlers_personal, "db", fake_db)
    msg = _msg()
    asyncio.run(handlers_personal.cmd_calendar(msg, _settings(mini_app_url="https://bot.example.com")))
    text = msg.answer.call_args.args[0]
    assert "webcal://bot.example.com/ical/abc123.ics" in text


def test_cmd_calendar_without_mini_app_url(monkeypatch):
    msg = _msg()
    asyncio.run(handlers_personal.cmd_calendar(msg, _settings(mini_app_url="")))
    assert "скоро будет" in msg.answer.call_args.args[0]


def test_yandex_email_sends_calendar_link_after_saving(monkeypatch):
    fake_db = SimpleNamespace(
        save_yandex_email=lambda tid, email: None,
        get_or_create_ical_token=lambda tid: "abc123",
    )
    monkeypatch.setattr(handlers_personal, "db", fake_db)
    state = AsyncMock()
    msg = _msg(text="student@yandex.ru")
    asyncio.run(handlers_personal.on_yandex_email(msg, state, _settings(mini_app_url="https://bot.example.com")))
    assert msg.answer.await_count == 2
    assert "сохранена" in msg.answer.call_args_list[0].args[0]
    assert "webcal://" in msg.answer.call_args_list[1].args[0]

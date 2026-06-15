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
pytest.importorskip("bot.handlers")

from shared.models import Deadline, ScheduleEvent  # noqa: E402
from bot import handlers  # noqa: E402
from bot.config import Settings  # noqa: E402
from bot.mappers import extraction_to_deadline  # noqa: E402

MSK = ZoneInfo("Europe/Moscow")


def _settings(**over) -> Settings:
    base = dict(
        bot_token="x", gigachat_credentials="x", fernet_key="x",
        supabase_url="x", supabase_service_key="x",
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
    monkeypatch.setattr(handlers, "db", fake_db)
    msg = _msg()
    asyncio.run(handlers.cmd_today(msg, _settings()))
    msg.answer.assert_awaited_once()
    assert "Физика" in msg.answer.call_args.args[0]


def test_group_message_saves_deadline(monkeypatch):
    captured = {}
    fake_db = SimpleNamespace(upsert_deadline=lambda d: captured.setdefault("d", d) or d)
    monkeypatch.setattr(handlers, "db", fake_db)
    monkeypatch.setattr(
        handlers, "extract_deadline",
        lambda text, llm, today: _fake_extraction(
            confidence=0.9, discipline_name="История", work_type="реферат",
            due_at=None, raw_quote=text,
        ),
    )
    msg = _msg(chat_type="supergroup", chat_id=-555, message_id=12, text="реферат к среде")
    asyncio.run(handlers.on_group_message(msg, _settings()))
    assert captured["d"].chat_id == -555 and captured["d"].source_message_id == 12


def test_group_message_skips_low_confidence(monkeypatch):
    fake_db = SimpleNamespace(upsert_deadline=AsyncMock())  # не должен вызваться
    monkeypatch.setattr(handlers, "db", fake_db)
    monkeypatch.setattr(
        handlers, "extract_deadline",
        lambda text, llm, today: _fake_extraction(confidence=0.2),
    )
    msg = _msg(chat_type="group", text="просто болтовня")
    asyncio.run(handlers.on_group_message(msg, _settings(confidence_threshold=0.7)))
    fake_db.upsert_deadline.assert_not_called()

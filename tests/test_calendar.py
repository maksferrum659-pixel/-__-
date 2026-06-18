"""Офлайн-тесты ICS-генератора и эндпоинтов /ical, /api/calendar-link (без сети и БД)."""
from __future__ import annotations

import pytest

pytest.importorskip("icalendar", reason="pip install icalendar>=5.0.0")
pytest.importorskip("fastapi", reason="pip install fastapi>=0.110.0")

from datetime import datetime
from zoneinfo import ZoneInfo

from shared.models import Deadline, ScheduleEvent
from ical.generator import events_to_ics

MSK = ZoneInfo("Europe/Moscow")


def _event(**kw) -> ScheduleEvent:
    base = dict(
        external_id="1", telegram_id=100, discipline_name="Матанализ",
        starts_at=datetime(2026, 9, 1, 9, 0, tzinfo=MSK),
        ends_at=datetime(2026, 9, 1, 10, 30, tzinfo=MSK),
    )
    base.update(kw)
    return ScheduleEvent(**base)


def _deadline(**kw) -> Deadline:
    base = dict(
        chat_id=100, discipline_name="История", work_type="ДЗ",
        due_at=datetime(2026, 9, 5, 23, 59, tzinfo=MSK),
        confidence=0.9,
    )
    base.update(kw)
    return Deadline(**base)


def test_events_to_ics_contains_vcalendar():
    ics = events_to_ics([_event()], [])
    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics


def test_schedule_event_maps_to_vevent():
    ics = events_to_ics([_event(room="3304", teacher="Иванов И.И.")], [])
    assert "BEGIN:VEVENT" in ics
    assert "Матанализ" in ics
    assert "3304" in ics


def test_deadline_has_valarm():
    ics = events_to_ics([], [_deadline()])
    assert "VALARM" in ics
    assert "История" in ics


def test_exam_has_category():
    ics = events_to_ics([_event(kind="Зачёт")], [])
    assert "CATEGORIES" in ics


def test_empty_input_returns_valid_calendar():
    ics = events_to_ics([], [])
    assert "BEGIN:VCALENDAR" in ics


def test_deadline_without_due_at_skipped():
    d = _deadline(due_at=None)
    ics = events_to_ics([], [d])
    assert ics.count("BEGIN:VEVENT") == 0


# ── HTTP-эндпоинты mini_app/server.py (с mock db) ───────────────────────────

def test_ical_endpoint_returns_200(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient
    import mini_app.server as server

    monkeypatch.setattr(server.db, "get_telegram_id_by_ical_token", lambda t: 100)
    monkeypatch.setattr(server.db, "get_schedule", lambda tid, since, until: [_event()])
    monkeypatch.setattr(server.db, "get_group_chat_id", lambda tid: None)
    monkeypatch.setattr(server.db, "list_deadlines", lambda chat_id, **kw: [])

    client = TestClient(server.app)
    resp = client.get("/ical/sometoken.ics")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]


def test_ical_endpoint_404_on_bad_token(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient
    import mini_app.server as server

    monkeypatch.setattr(server.db, "get_telegram_id_by_ical_token", lambda t: None)

    client = TestClient(server.app)
    resp = client.get("/ical/badtoken.ics")
    assert resp.status_code == 404


def test_calendar_link_returns_webcal_url(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient
    import mini_app.server as server

    monkeypatch.setattr(server, "_verify_init_data", lambda x: 100)
    monkeypatch.setattr(server.db, "get_or_create_ical_token", lambda tid: "tok123")

    client = TestClient(server.app)
    resp = client.get("/api/calendar-link", headers={"x-init-data": "irrelevant"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["webcal_url"].startswith("webcal://")
    assert data["webcal_url"].endswith("/ical/tok123.ics")
    assert data["https_url"].startswith("http")

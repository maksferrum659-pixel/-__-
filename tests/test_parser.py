"""Offline tests for the schedule parser (no network)."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from parser.portal import (
    PortalAuthError,
    authenticate,
    fetch_schedule,
    parse_calendar,
)
from shared.models import ScheduleEvent

SAMPLE = Path(__file__).resolve().parent.parent / "parser" / "samples" / "calendar_response.json"


@pytest.fixture()
def sample_payload() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


# ── parse_calendar ────────────────────────────────────────────────────────────

def test_parse_sample_returns_events(sample_payload):
    events = parse_calendar(sample_payload)
    assert len(events) == 7  # real capture: 2 day-buckets
    assert all(isinstance(e, ScheduleEvent) for e in events)


def test_required_fields_always_present(sample_payload):
    for event in parse_calendar(sample_payload):
        assert event.external_id, "external_id must be set"
        assert event.starts_at is not None
        assert event.ends_at is not None
        # datetimes are tz-aware (Europe/Moscow → UTC+3)
        assert event.starts_at.tzinfo is not None
        assert event.starts_at.utcoffset().total_seconds() == 3 * 3600


def test_events_sorted_by_start(sample_payload):
    events = parse_calendar(sample_payload)
    assert events == sorted(events, key=lambda e: e.starts_at)


def test_field_mapping(sample_payload):
    events = parse_calendar(sample_payload)
    by_id = {e.external_id: e for e in events}

    # id=5601: lecture in room 3304 (eventId is null in real data → falls back to id)
    lecture = by_id["5601"]
    assert lecture.discipline_name == "Цифровые технологии и тенденции развития"
    assert lecture.kind == "Лекция"  # "lecture" slug mapped to Russian
    assert lecture.room == "3304"
    assert lecture.teacher == "Преподаватель2 Имя2 Отч2"
    # startTime/endTime are Moscow wall-clock (UTC+3), not the UTC dateStart
    assert (lecture.starts_at.hour, lecture.starts_at.minute) == (9, 0)
    assert (lecture.ends_at.hour, lecture.ends_at.minute) == (10, 20)

    # id=5594: practical, location was null → room None
    practical = by_id["5594"]
    assert practical.kind == "Практика"  # "practical" slug mapped
    assert practical.room is None
    assert (practical.starts_at.hour, practical.starts_at.minute) == (7, 30)


def test_kind_slug_mapping():
    payload = {
        "results": [
            {
                "date": "2026-09-01",
                "events": [
                    {"id": 1, "name": "X", "type": "seminar", "startTime": "10:00", "endTime": "11:00"},
                    {"id": 2, "name": "Y", "type": "WeirdSlug", "startTime": "11:00", "endTime": "12:00"},
                ],
            }
        ]
    }
    by_id = {e.external_id: e for e in parse_calendar(payload)}
    assert by_id["1"].kind == "Семинар"
    assert by_id["2"].kind == "WeirdSlug"  # unknown slug passes through unchanged


def test_skips_incomplete_events():
    payload = {
        "items": [
            {"name": "no id/no time"},  # dropped: no external_id / times
            {
                "eventId": 999,
                "name": "valid",
                "date": "2026-06-15",
                "startTime": "08:00",
                "endTime": "09:30",
            },
        ]
    }
    events = parse_calendar(payload)
    assert [e.external_id for e in events] == ["999"]


def test_accepts_day_bucket_shape():
    payload = {
        "items": [
            {
                "date": "2026-06-15",
                "events": [
                    {"eventId": 1, "name": "A", "startTime": "10:00", "endTime": "11:00"},
                    {"eventId": 2, "name": "B", "startTime": "11:10", "endTime": "12:00"},
                ],
            }
        ]
    }
    events = parse_calendar(payload)
    assert [e.external_id for e in events] == ["1", "2"]
    assert events[0].starts_at.date() == date(2026, 6, 15)


# ── fetch_schedule (mocked transport, still offline) ──────────────────────────

def test_fetch_schedule_maps_response(sample_payload):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/private/scos/calendar"
        assert request.url.params["dateFrom"] == "2026-06-15"
        assert request.url.params["dateTo"] == "2026-06-20"
        assert request.headers["Cookie"] == "session=abc123"
        return httpx.Response(200, json=sample_payload)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://portal.test")
    events = fetch_schedule("session=abc123", date(2026, 6, 15), date(2026, 6, 20), client=client)
    assert len(events) == 7


def test_fetch_schedule_raises_on_expired_session():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"description": "Session expired"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://portal.test")
    with pytest.raises(PortalAuthError):
        fetch_schedule("bad", date(2026, 6, 15), date(2026, 6, 20), client=client)


# ── authenticate (mocked transport) ───────────────────────────────────────────

def test_authenticate_returns_cookie_string():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/public/users/login"
        body = json.loads(request.content)
        assert body == {"login": "user@example.com", "password": "secret"}
        return httpx.Response(200, json={"ok": True}, headers={"Set-Cookie": "session=xyz; Path=/"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://portal.test")
    token = authenticate("user@example.com", "secret", client=client)
    assert "session=xyz" in token


def test_authenticate_wrong_password_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"description": "Неверное имя пользователя или пароль"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://portal.test")
    with pytest.raises(PortalAuthError):
        authenticate("user@example.com", "wrong", client=client)

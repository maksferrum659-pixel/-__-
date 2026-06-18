import pytest
from datetime import datetime, timezone
from db import (
    get_or_create_user,
    save_portal_token,
    get_portal_token,
    upsert_schedule_events,
    get_schedule,
    upsert_deadline,
    list_deadlines,
    mark_deadline_done,
    list_users_with_token,
)
from shared.models import ScheduleEvent, Deadline

TEST_TELEGRAM_ID = 999999999
TEST_CHAT_ID = 888888888


def test_get_or_create_user():
    user = get_or_create_user(TEST_TELEGRAM_ID)
    assert user["telegram_id"] == TEST_TELEGRAM_ID
    # повторный вызов не создаёт дубль
    user2 = get_or_create_user(TEST_TELEGRAM_ID)
    assert user2["telegram_id"] == TEST_TELEGRAM_ID


def test_save_and_get_portal_token():
    get_or_create_user(TEST_TELEGRAM_ID)
    save_portal_token(TEST_TELEGRAM_ID, "encrypted_test_token")
    token = get_portal_token(TEST_TELEGRAM_ID)
    assert token == "encrypted_test_token"


def test_get_portal_token_none():
    token = get_portal_token(0)
    assert token is None


def test_upsert_schedule_events_idempotent():
    get_or_create_user(TEST_TELEGRAM_ID)
    event = ScheduleEvent(
        external_id="evt_001",
        telegram_id=TEST_TELEGRAM_ID,
        discipline_name="Математика",
        kind="лекция",
        starts_at=datetime(2024, 9, 1, 9, 0, tzinfo=timezone.utc),
        ends_at=datetime(2024, 9, 1, 10, 30, tzinfo=timezone.utc),
    )
    count1 = upsert_schedule_events(TEST_TELEGRAM_ID, [event])
    count2 = upsert_schedule_events(TEST_TELEGRAM_ID, [event])
    assert count1 == 1
    assert count2 == 1


def test_get_schedule():
    get_or_create_user(TEST_TELEGRAM_ID)
    events = get_schedule(
        TEST_TELEGRAM_ID,
        since=datetime(2024, 9, 1, tzinfo=timezone.utc),
        until=datetime(2024, 9, 2, tzinfo=timezone.utc),
    )
    assert isinstance(events, list)
    assert all(isinstance(e, ScheduleEvent) for e in events)


def test_upsert_deadline_idempotent():
    deadline = Deadline(
        chat_id=TEST_CHAT_ID,
        discipline_name="Физика",
        work_type="ДЗ",
        due_at=datetime(2024, 9, 10, tzinfo=timezone.utc),
        source_message_id=12345,
        confidence=0.9,
    )
    d1 = upsert_deadline(deadline)
    d2 = upsert_deadline(deadline)
    assert d1.id == d2.id  # не создаёт дубль


def test_list_deadlines():
    deadlines = list_deadlines(TEST_CHAT_ID)
    assert isinstance(deadlines, list)
    assert all(isinstance(d, Deadline) for d in deadlines)


def test_mark_deadline_done():
    get_or_create_user(TEST_TELEGRAM_ID)
    deadline = Deadline(
        chat_id=TEST_CHAT_ID,
        discipline_name="Химия",
        source_message_id=99999,
        confidence=0.8,
    )
    d = upsert_deadline(deadline)
    mark_deadline_done(TEST_TELEGRAM_ID, d.id, True)


def test_list_users_with_token():
    get_or_create_user(TEST_TELEGRAM_ID)
    save_portal_token(TEST_TELEGRAM_ID, "some_token")
    users = list_users_with_token()
    assert TEST_TELEGRAM_ID in users
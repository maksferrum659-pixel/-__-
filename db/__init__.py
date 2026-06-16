from datetime import datetime
from typing import Optional
from .client import supabase
from shared.models import ScheduleEvent, Deadline


def get_or_create_user(telegram_id: int) -> dict:
    result = supabase.table("users").upsert(
        {"telegram_id": telegram_id},
        on_conflict="telegram_id"
    ).execute()
    return result.data[0]


def save_portal_token(telegram_id: int, encrypted_token: str) -> None:
    supabase.table("users").upsert({
        "telegram_id": telegram_id,
        "portal_token_encrypted": encrypted_token
    }, on_conflict="telegram_id").execute()


def get_portal_token(telegram_id: int) -> Optional[str]:
    result = supabase.table("users").select("portal_token_encrypted").eq(
        "telegram_id", telegram_id
    ).execute()
    if result.data:
        return result.data[0].get("portal_token_encrypted")
    return None


def upsert_schedule_events(telegram_id: int, events: list[ScheduleEvent]) -> int:
    if not events:
        return 0
    rows = [
        {
            "external_id": e.external_id,
            "telegram_id": telegram_id,
            "discipline_name": e.discipline_name,
            "kind": e.kind,
            "starts_at": e.starts_at.isoformat(),
            "ends_at": e.ends_at.isoformat(),
            "room": e.room,
            "teacher": e.teacher,
            "online_link": e.online_link,
        }
        for e in events
    ]
    result = supabase.table("schedule_events").upsert(
        rows, on_conflict="external_id,telegram_id"
    ).execute()
    return len(result.data)


def get_schedule(telegram_id: int, since: datetime, until: datetime) -> list[ScheduleEvent]:
    result = supabase.table("schedule_events").select("*").eq(
        "telegram_id", telegram_id
    ).gte("starts_at", since.isoformat()).lte("starts_at", until.isoformat()).execute()
    return [ScheduleEvent(**row) for row in result.data]


def upsert_deadline(deadline: Deadline) -> Deadline:
    row = deadline.model_dump(exclude={"id"})
    if row.get("due_at"):
        row["due_at"] = deadline.due_at.isoformat()
    result = supabase.table("deadlines").upsert(
        row, on_conflict="chat_id,source_message_id"
    ).execute()
    return Deadline(**result.data[0])


def list_deadlines(chat_id: int, only_open: bool = True) -> list[Deadline]:
    query = supabase.table("deadlines").select(
        "*, user_deadline_status(done)"
    ).eq("chat_id", chat_id)
    result = query.execute()
    deadlines = []
    for row in result.data:
        row.pop("user_deadline_status", None)
        deadlines.append(Deadline(**row))
    return deadlines


def mark_deadline_done(telegram_id: int, deadline_id: str, done: bool) -> None:
    supabase.table("user_deadline_status").upsert({
        "telegram_id": telegram_id,
        "deadline_id": deadline_id,
        "done": done
    }, on_conflict="telegram_id,deadline_id").execute()


def list_users_with_token() -> list[int]:
    result = supabase.table("users").select("telegram_id").not_.is_(
        "portal_token_encrypted", "null"
    ).execute()
    return [row["telegram_id"] for row in result.data]


def get_or_create_ical_token(telegram_id: int) -> str:
    """Вернуть ical_token пользователя (UUID). Требует миграции 002_add_ical_token.sql."""
    import uuid as _uuid
    get_or_create_user(telegram_id)
    result = supabase.table("users").select("ical_token").eq(
        "telegram_id", telegram_id
    ).execute()
    token = result.data[0].get("ical_token") if result.data else None
    if token:
        return token
    # Колонка есть (DEFAULT gen_random_uuid), но значение NULL — обновляем вручную
    new_token = str(_uuid.uuid4())
    supabase.table("users").update({"ical_token": new_token}).eq(
        "telegram_id", telegram_id
    ).execute()
    return new_token


def get_telegram_id_by_ical_token(token: str) -> Optional[int]:
    result = supabase.table("users").select("telegram_id").eq(
        "ical_token", token
    ).execute()
    if result.data:
        return result.data[0]["telegram_id"]
    return None
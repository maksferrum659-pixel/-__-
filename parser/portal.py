"""
rr-edu.ranepa.ru schedule parser.

Pure library — §6 of CONTRACT.md. No DB access, no secret storage.

Auth scheme (reverse-engineered from the portal's public assets; the full,
sanitised capture lives in ``parser/SAMPLE_AUTH.md``):

* The session is **cookie-based**. The login endpoint sets a session cookie;
  the calendar endpoint answers ``401 {"description": "Session expired"}``
  when it is missing.
* ``POST /api/v1/public/users/login`` with JSON body ``{"login", "password"}``.
  Wrong credentials → ``403 "Неверное имя пользователя или пароль"``.
* ``GET /api/v1/private/scos/calendar?dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD&perPage=70``.

`authenticate` returns a **cookie string** (``"name=value; name2=value2"``) — a
session handle, never the password. `fetch_schedule` sends it back as the
``Cookie`` header.

Note on ``telegram_id``: the frozen signature of `fetch_schedule` does not
receive it, and `ScheduleEvent.telegram_id` is required. The parser cannot know
whose Telegram account this is, so it fills the placeholder
``UNKNOWN_TELEGRAM_ID`` (0). The bot's sync task owns the real value and passes
it to ``db.upsert_schedule_events(telegram_id, events)``, which writes the
column from its own argument (see db/__init__.py), so the placeholder never
reaches Supabase.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import httpx

from shared.models import ScheduleEvent

# ── configuration ─────────────────────────────────────────────────────────────

PORTAL_BASE_URL = os.environ.get("PORTAL_BASE_URL", "https://rr-edu.ranepa.ru")
LOGIN_PATH = "/api/v1/public/users/login"
CALENDAR_PATH = "/api/v1/private/scos/calendar"
DEFAULT_PER_PAGE = 70
DEFAULT_TIMEOUT = 30.0

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

#: Placeholder owner id; the real telegram_id is supplied later by db.upsert_*.
UNKNOWN_TELEGRAM_ID = 0

#: Portal `type` slugs → human-readable Russian kind (CONTRACT.md §5 examples).
#: Unknown slugs fall through to their raw value.
KIND_BY_TYPE: dict[str, str] = {
    "lecture": "Лекция",
    "practical": "Практика",
    "practice": "Практика",
    "seminar": "Семинар",
    "lab": "Лабораторная",
    "laboratory": "Лабораторная",
    "consultation": "Консультация",
    "exam": "Экзамен",
    "credit": "Зачёт",
    "test": "Зачёт",
}


# ── errors ────────────────────────────────────────────────────────────────────

class PortalError(RuntimeError):
    """Base error for any portal interaction failure."""


class PortalAuthError(PortalError):
    """Login failed or the session token is invalid/expired."""


# ── public API (§6, frozen signatures) ───────────────────────────────────────

def authenticate(login: str, password: str, *, client: httpx.Client | None = None) -> str:
    """Log into the portal and return a session **cookie string**.

    The returned value is the ``Cookie`` header to replay on later requests —
    never the password. ``client`` is an injection point for tests; production
    callers omit it.

    Raises:
        PortalAuthError: wrong credentials, or no session cookie was issued.
        PortalError: any other transport/HTTP failure.
    """
    owned = client is None
    cli = client or _make_client()
    try:
        try:
            response = cli.post(LOGIN_PATH, json={"login": login, "password": password})
        except httpx.HTTPError as exc:  # network/timeout/etc.
            raise PortalError(f"Login request failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise PortalAuthError("Неверное имя пользователя или пароль")
        if response.status_code >= 400:
            raise PortalError(_describe(response))

        cookie = _serialize_cookies(cli.cookies)
        if not cookie:
            # Some deployments hand back a bearer/session token in the body
            # instead of (or in addition to) a cookie. Fall back to that.
            cookie = _token_from_body(response)
        if not cookie:
            raise PortalAuthError("Login succeeded but no session cookie/token was returned")
        return cookie
    finally:
        if owned:
            cli.close()


def fetch_schedule(
    token: str,
    since: date,
    until: date,
    *,
    client: httpx.Client | None = None,
) -> list[ScheduleEvent]:
    """Fetch the user's calendar for ``[since, until]`` and map it to events.

    ``token`` is the cookie string returned by `authenticate`. ``client`` is an
    injection point for tests.

    Raises:
        PortalAuthError: the session is missing/expired (HTTP 401).
        PortalError: any other transport/HTTP failure.
    """
    params = {
        "dateFrom": since.isoformat(),
        "dateTo": until.isoformat(),
        "perPage": DEFAULT_PER_PAGE,
    }
    headers = {"Cookie": token}

    owned = client is None
    cli = client or _make_client()
    try:
        try:
            response = cli.get(CALENDAR_PATH, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise PortalError(f"Calendar request failed: {exc}") from exc

        if response.status_code == 401:
            raise PortalAuthError("Session expired")
        if response.status_code >= 400:
            raise PortalError(_describe(response))

        try:
            payload = response.json()
        except ValueError as exc:
            raise PortalError(f"Calendar response was not JSON: {exc}") from exc
    finally:
        if owned:
            cli.close()

    return parse_calendar(payload)


# ── mapping (pure, offline-testable) ──────────────────────────────────────────

def parse_calendar(payload: Any, *, telegram_id: int = UNKNOWN_TELEGRAM_ID) -> list[ScheduleEvent]:
    """Map a raw calendar JSON payload to ``list[ScheduleEvent]``.

    Tolerant to two response shapes:
      * a flat list of events (optionally wrapped in ``items``/``data``/``events``);
      * day buckets ``[{"date": ..., "events": [...]}]``.

    Events that cannot yield ``external_id`` + ``starts_at`` + ``ends_at`` are
    skipped, so every returned event has those fields populated.
    """
    events: list[ScheduleEvent] = []
    for raw in _iter_events(payload):
        event = _to_event(raw, telegram_id=telegram_id)
        if event is not None:
            events.append(event)
    events.sort(key=lambda e: e.starts_at)
    return events


def _iter_events(payload: Any, inherited_date: str | None = None) -> Iterable[dict]:
    """Yield event dicts, flattening day-bucket wrappers and common envelopes."""
    if payload is None:
        return
    if isinstance(payload, dict):
        # Day bucket: {"date": ..., "events": [...]}
        if "events" in payload and "eventId" not in payload and "id" not in payload:
            bucket_date = payload.get("date") or inherited_date
            yield from _iter_events(payload.get("events"), bucket_date)
            return
        # Envelope: {"items"/"data"/"results": [...]} (also paginated lists)
        for key in ("items", "data", "results"):
            if isinstance(payload.get(key), list):
                yield from _iter_events(payload[key], inherited_date)
                return
        # Otherwise it's a single event.
        if inherited_date and "date" not in payload:
            payload = {**payload, "date": inherited_date}
        yield payload
        return
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_events(item, inherited_date)


def _to_event(raw: dict, *, telegram_id: int) -> ScheduleEvent | None:
    if not isinstance(raw, dict):
        return None

    # `eventId` is often null for schedule entries; `id` (row PK) and `key`
    # (UUID) are the stable portal identifiers used for idempotent upsert.
    external_id = _first(raw, "eventId", "id", "key", "externalId")
    starts_at = _combine(
        _first(raw, "date", "day", "dateStart"),
        _first(raw, "startTime", "timeStart", "start"),
    )
    ends_at = _combine(
        _first(raw, "date", "day", "dateEnd"),
        _first(raw, "endTime", "timeEnd", "end"),
    )
    if external_id is None or starts_at is None or ends_at is None:
        return None

    return ScheduleEvent(
        external_id=str(external_id),
        telegram_id=telegram_id,
        discipline_name=str(_first(raw, "name", "title", "discipline", "subject") or ""),
        kind=_map_kind(_first(raw, "type", "kind", "lessonType")),
        starts_at=starts_at,
        ends_at=ends_at,
        room=_nested_name(_first(raw, "location", "room", "place")),
        teacher=_teacher_name(raw.get("teacher")),
        online_link=_clean(_first(raw, "meetingUrl", "onlineUrl", "online_link", "link")),
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_client() -> httpx.Client:
    return httpx.Client(
        base_url=PORTAL_BASE_URL,
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        headers={"Accept": "application/json"},
    )


def _serialize_cookies(cookies: httpx.Cookies) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def _token_from_body(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    for key in ("token", "access_token", "session_token", "sessionToken"):
        value = body.get(key)
        if value:
            return str(value)
    return ""


def _describe(response: httpx.Response) -> str:
    try:
        body = response.json()
        detail = body.get("description") or body.get("name") or body
    except ValueError:
        detail = response.text[:200]
    return f"HTTP {response.status_code}: {detail}"


def _first(raw: dict, *keys: str) -> Any:
    for key in keys:
        if raw.get(key) not in (None, ""):
            return raw[key]
    return None


def _clean(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _map_kind(value: Any) -> str | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    return KIND_BY_TYPE.get(cleaned.lower(), cleaned)


def _nested_name(value: Any) -> str | None:
    """``location`` may be a string or an object like ``{"name": "ауд. 312"}``."""
    if isinstance(value, dict):
        return _clean(value.get("name") or value.get("title"))
    return _clean(value)


def _teacher_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return _clean(value.get("fullName") or value.get("name"))
    if isinstance(value, list) and value:
        names = [_teacher_name(v) for v in value]
        joined = ", ".join(n for n in names if n)
        return joined or None
    return _clean(value)


def _combine(date_value: Any, time_value: Any) -> datetime | None:
    """Build a tz-aware (Europe/Moscow) datetime from a date + time pair.

    Accepts ``date`` as ``YYYY-MM-DD`` and ``time`` as ``HH:MM[:SS]``. If either
    field already carries a full ISO datetime, it is used directly. Naive results
    are localised to Europe/Moscow.
    """
    # Full ISO datetime already provided?
    for candidate in (time_value, date_value):
        if isinstance(candidate, str) and "T" in candidate:
            try:
                dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            except ValueError:
                continue
            return dt if dt.tzinfo else dt.replace(tzinfo=MOSCOW_TZ)

    if not date_value or not time_value:
        return None
    try:
        day = date.fromisoformat(str(date_value)[:10])
        parts = str(time_value).split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        return None
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=MOSCOW_TZ)

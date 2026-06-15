"""
Public parser API — §6 of CONTRACT.md.

This is a PURE library: it talks to the rr-edu.ranepa.ru portal and returns
`shared.models.ScheduleEvent` objects. It never touches the database and never
stores credentials.

    authenticate(login, password) -> str
    fetch_schedule(token, since, until) -> list[ScheduleEvent]
"""

from parser.portal import (
    PortalAuthError,
    PortalError,
    authenticate,
    fetch_schedule,
    parse_calendar,
)

__all__ = [
    "authenticate",
    "fetch_schedule",
    "parse_calendar",
    "PortalError",
    "PortalAuthError",
]

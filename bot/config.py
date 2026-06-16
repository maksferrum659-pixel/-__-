"""Чтение конфигурации из окружения (.env) — CONTRACT.md §8.

Здесь же — настраиваемые параметры поведения бота (пороги/интервалы).
Значения по умолчанию ПРОВИЗОРНЫЕ: контрактом не зафиксированы, подтвердить с командой.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta

try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:  # python-dotenv ещё не установлен — читаем голое окружение
    pass


class ConfigError(RuntimeError):
    """Не хватает обязательной переменной окружения."""


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(
            f"Не задана обязательная переменная окружения {name!r}. "
            f"См. .env.example и CONTRACT.md §8."
        )
    return value


@dataclass(frozen=True)
class Settings:
    # --- секреты / адреса (CONTRACT.md §8) ---
    bot_token: str
    gigachat_credentials: str
    fernet_key: str
    supabase_url: str
    supabase_service_key: str
    portal_base_url: str = "https://rr-edu.ranepa.ru"
    calendar_base_url: str = ""  # URL сервера ICS-фида, напр. https://yourbot.ru

    # --- настраиваемое поведение (ПРОВИЗОРНЫЕ дефолты, не из контракта) ---
    timezone: str = "Europe/Moscow"
    confidence_threshold: float = 0.7          # ниже — дедлайн не сохраняем
    schedule_sync_interval_hours: int = 6      # как часто синкать расписание
    reminder_scan_interval_minutes: int = 15   # как часто проверять, кому слать напоминание
    # за сколько до дедлайна/пары напоминать:
    reminder_lead_times: tuple[timedelta, ...] = (timedelta(hours=24), timedelta(hours=1))


def load_settings() -> Settings:
    """Собрать Settings из окружения. Бросает ConfigError при нехватке секретов."""
    return Settings(
        bot_token=_require("BOT_TOKEN"),
        gigachat_credentials=_require("GIGACHAT_CREDENTIALS"),
        fernet_key=_require("FERNET_KEY"),
        supabase_url=_require("SUPABASE_URL"),
        supabase_service_key=_require("SUPABASE_SERVICE_KEY"),
        portal_base_url=os.getenv("PORTAL_BASE_URL", "https://rr-edu.ranepa.ru"),
        calendar_base_url=os.getenv("CALENDAR_BASE_URL", ""),
    )

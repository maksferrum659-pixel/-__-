"""Шифрование токена портала (CONTRACT.md §6).

Fernet-шифрование (симметричное, AES-128-CBC + HMAC). Ключ — в `FERNET_KEY`
(см. .env.example §8). Сгенерировать: ``Fernet.generate_key().decode()``.

Ключ читается ЛЕНИВО (на первый вызов), чтобы импорт модуля не падал в окружении
без секретов (тесты, CI). Сам токен в БД хранит `db.save_portal_token`; открытый
пароль не шифруем и нигде не держим.
"""
from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet

try:  # подхватываем .env, если он есть; в проде переменные уже в окружении
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:  # python-dotenv не обязателен
    pass


class SecurityError(RuntimeError):
    """Проблема с ключом шифрования или порченый шифротекст."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.getenv("FERNET_KEY")
    if not key:
        raise SecurityError(
            "Не задан FERNET_KEY. Сгенерируй: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise SecurityError(f"Некорректный FERNET_KEY: {exc}") from exc


def encrypt_token(plain: str) -> str:
    """Зашифровать строку токена/cookie портала → строка для хранения в БД."""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_token(enc: str) -> str:
    """Расшифровать то, что вернул `encrypt_token`."""
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(enc.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecurityError("Не удалось расшифровать токен (неверный ключ или данные)") from exc

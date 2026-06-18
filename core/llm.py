"""LLM-клиент (CONTRACT.md §6).

Протокол `LLMClient` + реализация `GigaChatClient` (основной провайдер по §2;
запасной — YandexGPT — реализуется тем же протоколом при необходимости).

Конструктор сети НЕ трогает: OAuth-токен берётся лениво на первый `.complete()`
и кэшируется до истечения. Поэтому `GigaChatClient()` безопасно создавать на
импорте (как делает bot.handlers), даже без секретов в окружении — ошибка всплывёт
только при реальном вызове.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Protocol, runtime_checkable

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:
    pass

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


@runtime_checkable
class LLMClient(Protocol):
    """Минимальный контракт LLM-клиента: один синхронный вызов завершения."""

    def complete(self, system: str, user: str) -> str: ...


class LLMError(RuntimeError):
    """Сбой авторизации или запроса к LLM."""


class GigaChatClient:
    """Клиент GigaChat (Sberbank). Реализует протокол `LLMClient`.

    Args:
        credentials: Basic-креды (base64 client_id:secret). По умолчанию из
            ``GIGACHAT_CREDENTIALS``.
        scope: область доступа, по умолчанию из ``GIGACHAT_SCOPE`` или
            ``GIGACHAT_API_PERS`` (физлица).
        model: имя модели GigaChat.
        verify_ssl: проверка TLS. У GigaChat цепочка на корневом сертификате
            Минцифры РФ; по умолчанию ``False`` (как в их примерах). Для прода
            лучше подложить russian_trusted_root_ca и включить проверку.
    """

    def __init__(
        self,
        credentials: str | None = None,
        *,
        scope: str | None = None,
        model: str = "GigaChat",
        verify_ssl: bool = False,
        timeout: float = 30.0,
    ) -> None:
        self._credentials = credentials or os.getenv("GIGACHAT_CREDENTIALS")
        self._scope = scope or os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self._model = model
        self._verify = verify_ssl
        self._timeout = timeout
        self._token: str | None = None
        self._token_exp: float = 0.0

    # ── auth ──────────────────────────────────────────────────────────────
    def _access_token(self) -> str:
        # Запас 60 с до фактического истечения.
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        if not self._credentials:
            raise LLMError("Не задан GIGACHAT_CREDENTIALS (см. .env.example §8).")

        try:
            response = httpx.post(
                OAUTH_URL,
                headers={
                    "Authorization": f"Basic {self._credentials}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"scope": self._scope},
                verify=self._verify,
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"GigaChat OAuth failed: {exc}") from exc

        self._token = payload["access_token"]
        # expires_at в миллисекундах epoch; падать на формат не будем.
        exp_ms = payload.get("expires_at")
        self._token_exp = (exp_ms / 1000) if exp_ms else time.time() + 1800
        return self._token

    # ── LLMClient ─────────────────────────────────────────────────────────
    def complete(self, system: str, user: str) -> str:
        """Один проход: system+user → текст ответа модели."""
        token = self._access_token()
        try:
            response = httpx.post(
                CHAT_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.1,
                },
                verify=self._verify,
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"GigaChat completion failed: {exc}") from exc

        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Неожиданный ответ GigaChat: {payload!r}") from exc

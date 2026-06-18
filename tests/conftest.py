"""Бутстрап тестов: путь к пакету бота и фолбэк-стабы общих модулей.

Реальные shared/core/db/parser (когда появятся в ветке) имеют приоритет —
стабы из _setup/stubs добавляются В КОНЕЦ sys.path и только если папка существует.
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)  # чтобы импортировался пакет `bot`

_STUBS = os.path.join(_ROOT, "_setup", "stubs")
if os.path.isdir(_STUBS) and _STUBS not in sys.path:
    sys.path.append(_STUBS)  # фолбэк: shared/core/db/parser для локального дева

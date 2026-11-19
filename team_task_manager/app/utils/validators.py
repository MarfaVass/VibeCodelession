"""Валидаторы пользовательского ввода и защиты от переполнения сообщений."""

from __future__ import annotations

import re

# Лимит длины текстового сообщения Telegram.
TG_MESSAGE_LIMIT = 4096
# На практике оставляем запас под служебный текст и разметку.
SAFE_TEXT_LIMIT = 3900

# Разрешённые символы названия задачи: буквы (в т.ч. кириллица), цифры,
# пробелы и типичная пунктуация.
_TITLE_RE = re.compile(r"^[\w\s\.,:;!\?а-яёА-ЯЁ(){}\[\]\+\-*/#№@«»'\"\\/&%$ё]+$", re.UNICODE)


def validate_title(title: str) -> str | None:
    """Проверяет название задачи. Возвращает текст ошибки или None."""
    title = title.strip()
    if not title:
        return "Название не может быть пустым. Введите текст."
    if len(title) < 3:
        return "Название слишком короткое — минимум 3 символа."
    if len(title) > 100:
        return f"Название слишком длинное ({len(title)} символов). Максимум — 100."
    return None


def validate_description(text: str) -> str | None:
    """Проверяет описание задачи. Возвращает текст ошибки или None."""
    text = text.strip()
    if len(text) > 1500:
        return f"Описание слишком длинное ({len(text)} символов). Максимум — 1500."
    return None


def clamp_text(text: str, limit: int = SAFE_TEXT_LIMIT) -> str:
    """Обрезает текст, чтобы сообщение не превысило лимит Telegram."""
    if len(text) <= limit:
        return text
    return text[:limit - 1] + "…"


def safe_username(username: str | None) -> str:
    """Экранирует username для безопасного вывода в сообщениях."""
    if not username:
        return "—"
    return username if re.fullmatch(r"^[\w.]{2,32}$", username) else "—"

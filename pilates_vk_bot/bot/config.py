"""Конфигурация проекта.

Все настройки берутся из файла ``.env`` (если он существует) и переменных
окружения. Значения по умолчанию подобраны так, чтобы бот можно было
запустить без правки исходного кода.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Корень проекта: .../pilates_vk_bot
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """Единый объект настроек приложения."""

    vk_token: str | None = None
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-32k"
    db_path: Path = PROJECT_ROOT / "data" / "bookings.db"
    prompt_path: Path = PROJECT_ROOT / "bot" / "prompts" / "system_prompt.txt"
    knowledge_path: Path = PROJECT_ROOT / "bot" / "knowledge" / "documents"

    # Таймауты и ограничения
    # num_predict (лимит токенов ответа) — главный регулятор времени ответа:
    # модели на CPU генерируют ~4–6 ток/с, поэтому лимит держат низким.
    ai_timeout: float = 90.0
    ai_max_tokens: int = 150
    ai_max_answer_len: int = 3800  # лимит сообщения VK — 4096 символов



def load_settings() -> Settings:
    """Собрать настройки из окружения.

    Дополнительно поддерживаются необязательные переменные:

    * ``DB_PATH`` — путь к файлу базы данных SQLite;
    * ``AI_TIMEOUT`` — таймаут запроса к Ollama в секундах;
    * ``AI_MAX_TOKENS`` — ограничение длины ответа модели.
    """

    db_path_value = os.getenv("DB_PATH")
    db_path = Path(db_path_value) if db_path_value else PROJECT_ROOT / "data" / "bookings.db"

    try:
        ai_timeout = float(os.getenv("AI_TIMEOUT", "90"))
    except ValueError:
        ai_timeout = 90.0

    try:
        ai_max_tokens = int(os.getenv("AI_MAX_TOKENS", "400"))
    except ValueError:
        ai_max_tokens = 400

    return Settings(
        vk_token=os.getenv("VK_TOKEN") or None,
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b-32k"),
        db_path=db_path,
        ai_timeout=ai_timeout,
        ai_max_tokens=ai_max_tokens,
    )


def load_system_prompt(path: Path | None = None) -> str:
    """Загрузить системный промпт (для ручной проверки окружения)."""

    from .prompts import load_prompt

    return load_prompt("system") if path is None else path.read_text(encoding="utf-8").strip()
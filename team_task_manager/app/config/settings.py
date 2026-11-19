"""Конфигурация приложения.

Читает переменные окружения из файла .env (через python-dotenv) и
предоставляет единый объект настроек Settings для всего проекта.

Важно: содержимое .env никогда не выводится в консоль и логи.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Иммутабельный контейнер настроек приложения."""

    bot_token: str
    admin_ids: frozenset[int]
    timezone: str
    database_path: Path
    log_level: str
    backup_enabled: bool

    @property
    def is_configured(self) -> bool:
        """True, если токен и список администраторов заполнены."""
        return bool(self.bot_token) and bool(self.admin_ids)


def _parse_admin_ids(raw: str | None) -> frozenset[int]:
    """Разбирает строку '123456789,987654321' в множество int.

    Пустые значения и мусор молча пропускаются — проверка
    «администраторы заданы» выполняется отдельно.
    """
    if not raw:
        return frozenset()
    ids: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            ids.add(int(chunk))
    return frozenset(ids)


def load_settings(env_dir: Path | None = None) -> Settings:
    """Загружает настройки из .env (или переменных окружения процесса).

    :param env_dir: каталог, где ищется файл .env (по умолчанию — корень проекта).
    """
    if env_dir is None:
        env_dir = Path(__file__).resolve().parents[2]  # корень проекта
    load_dotenv(env_dir / ".env")

    settings = Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS")),
        timezone=os.getenv("TIMEZONE", "Europe/Stockholm").strip(),
        database_path=Path(os.getenv("DATABASE_PATH", "data/tasks.db").strip()),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        backup_enabled=os.getenv("BACKUP_ENABLED", "true").strip().lower()
        in {"1", "true", "yes", "да"},
    )
    return settings

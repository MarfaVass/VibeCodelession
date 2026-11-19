"""Репозиторий пользователей команды."""

from __future__ import annotations

import logging
from typing import Any

from ..database import Database

logger = logging.getLogger(__name__)


def _to_bool(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Приводит is_active из int (0/1, как отдаёт SQLite) к bool.

    Код и тесты ожидают настоящий bool (например, ``is False`` в проверках
    доступа), поэтому конвертация выполняется здесь — на выходе репозитория —
    и не дублируется по всем потребителям.
    """
    if row is not None and "is_active" in row:
        row["is_active"] = bool(row["is_active"])
    return row


class UserRepository:
    """Регистрация участников, роли, активация/деактивация."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def ensure_registered(
        self, tg_id: int, username: str | None, full_name: str
    ) -> dict[str, Any]:
        """Возвращает пользователя, регистрируя его при первом контакте.

        Обновляет username и имя при изменении в Telegram-профиле.
        Новые участники всегда получают роль 'member'; роль admin
        назначается отдельно из ADMIN_IDS (см. AccessControlMiddleware).
        """
        existing = await self.get(tg_id)
        if existing is None:
            await self.db.execute(
                """
                INSERT INTO users (id, username, full_name, role, is_active, joined_at)
                VALUES (?, ?, ?, 'member', 1, datetime('now'))
                """,
                (tg_id, username, full_name),
            )
            logger.info("Зарегистрирован новый участник id=%s (%s)", tg_id, full_name)
            # Перечитываем из БД: метод обязан вернуть данные пользователя
            # и при первой регистрации (middleware читает user["role"]).
            existing = await self.get(tg_id)
        else:
            # Профиль мог измениться — синхронизируем имя/username.
            if existing["username"] != username or existing["full_name"] != full_name:
                await self.db.execute(
                    "UPDATE users SET username = ?, full_name = ? WHERE id = ?",
                    (username, full_name, tg_id),
                )
            existing = await self.get(tg_id)
        return existing

    async def get(self, tg_id: int) -> dict[str, Any] | None:
        """Пользователь по Telegram ID или None."""
        return _to_bool(
            await self.db.fetch_one("SELECT * FROM users WHERE id = ?", (tg_id,))
        )

    async def get_by_name(self, full_name: str) -> dict[str, Any] | None:
        """Пользователь по имени (используется при назначении исполнителя)."""
        return _to_bool(
            await self.db.fetch_one(
                "SELECT * FROM users WHERE full_name = ? AND is_active = 1",
                (full_name,),
            )
        )

    async def list_active(self) -> list[dict[str, Any]] | None:
        """Список активных участников (алфавитный порядок)."""
        rows = await self.db.fetch_all(
            "SELECT * FROM users WHERE is_active = 1 ORDER BY full_name"
        )
        return [_to_bool(row) for row in rows]

    async def list_all(self) -> list[dict[str, Any]]:
        """Список всех участников, включая деактивированных."""
        rows = await self.db.fetch_all("SELECT * FROM users ORDER BY full_name")
        return [_to_bool(row) for row in rows]

    async def set_role(self, tg_id: int, role: str) -> None:
        """Меняет роль пользователя ('admin' или 'member')."""
        if role not in {"admin", "member"}:
            raise ValueError(f"Недопустимая роль: {role}")
        await self.db.execute("UPDATE users SET role = ? WHERE id = ?", (role, tg_id))
        logger.info("Роль пользователя id=%s изменена на %s", tg_id, role)

    async def set_active(self, tg_id: int, is_active: bool) -> None:
        """Деактивирует (не удаляет!) участника команды."""
        await self.db.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, tg_id),
        )
        logger.info("Активность участника id=%s => %s", tg_id, is_active)

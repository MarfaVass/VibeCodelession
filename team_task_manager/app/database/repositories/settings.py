"""Репозиторий справочников: категории, статусы, приоритеты, настройки key/value.

Администратор управляет этими списками через интерфейс бота.
Код не «знает» конкретные названия статусов/категорий — любые операции
выполняются над текущими значениями справочников в БД.
"""

from __future__ import annotations

import logging
from typing import Any

from ..database import Database

logger = logging.getLogger(__name__)


class SettingsRepository:
    """CRUD справочников + настройки key/value."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Настройки key/value
    # ------------------------------------------------------------------
    async def get_setting(self, key: str) -> str | None:
        """Значение настройки по ключу."""
        return await self.db.fetch_val(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )

    async def set_setting(self, key: str, value: str) -> None:
        """Сохраняет настройку (вставка или обновление)."""
        await self.db.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    # ------------------------------------------------------------------
    # Категории
    # ------------------------------------------------------------------
    async def list_categories(self, only_active: bool = False) -> list[dict[str, Any]]:
        where = " WHERE is_active = 1" if only_active else ""
        return await self.db.fetch_all(
            "SELECT * FROM categories" + where + " ORDER BY name"
        )

    async def get_category(self, category_id: int) -> dict[str, Any] | None:
        return await self.db.fetch_one("SELECT * FROM categories WHERE id = ?", (category_id,))

    async def add_category(self, name: str) -> bool:
        """Добавляет категорию. False — если такое имя уже есть."""
        try:
            await self.db.execute(
                "INSERT INTO categories (name, is_active) VALUES (?, 1)", (name,)
            )
            logger.info("Добавлена категория '%s'", name)
            return True
        except Exception:  # UNIQUE constraint — имя уже существует
            return False

    async def rename_category(self, category_id: int, new_name: str) -> bool:
        try:
            await self.db.execute(
                "UPDATE categories SET name = ? WHERE id = ?", (new_name, category_id)
            )
            return True
        except Exception:
            return False

    async def set_category_active(self, category_id: int, is_active: bool) -> None:
        """Включает/выключает категорию (безопасное отключение вместо удаления)."""
        await self.db.execute(
            "UPDATE categories SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, category_id),
        )
        state = "включена" if is_active else "отключена"
        logger.info("Категория id=%s %s", category_id, state)

    # ------------------------------------------------------------------
    # Статусы
    # ------------------------------------------------------------------
    async def list_statuses(self, only_active: bool = False) -> list[dict[str, Any]]:
        where = " WHERE is_active = 1" if only_active else ""
        return await self.db.fetch_all(
            "SELECT * FROM statuses" + where + " ORDER BY sort_order, id"
        )

    async def get_status(self, status_id: int) -> dict[str, Any] | None:
        return await self.db.fetch_one("SELECT * FROM statuses WHERE id = ?", (status_id,))

    async def add_status(self, name: str, is_final: bool = False) -> bool:
        """Добавляет статус в конец списка. False — если имя занято."""
        next_order = int(
            await self.db.fetch_val("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM statuses")
        )
        try:
            await self.db.execute(
                "INSERT INTO statuses (name, sort_order, is_final, is_active) VALUES (?, ?, ?, 1)",
                (name, next_order, 1 if is_final else 0),
            )
            logger.info("Добавлен статус '%s' (final=%s)", name, is_final)
            return True
        except Exception:
            return False

    async def rename_status(self, status_id: int, new_name: str) -> bool:
        try:
            await self.db.execute(
                "UPDATE statuses SET name = ? WHERE id = ?", (new_name, status_id)
            )
            return True
        except Exception:
            return False

    async def set_status_active(self, status_id: int, is_active: bool) -> None:
        await self.db.execute(
            "UPDATE statuses SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, status_id),
        )
        logger.info("Статус id=%s => is_active=%s", status_id, is_active)

    # ------------------------------------------------------------------
    # Приоритеты
    # ------------------------------------------------------------------
    async def list_priorities(self, only_active: bool = False) -> list[dict[str, Any]]:
        where = " WHERE is_active = 1" if only_active else ""
        return await self.db.fetch_all(
            "SELECT * FROM priorities" + where + " ORDER BY sort_order, id"
        )

    async def get_priority(self, priority_id: int) -> dict[str, Any] | None:
        return await self.db.fetch_one("SELECT * FROM priorities WHERE id = ?", (priority_id,))

    async def add_priority(self, name: str) -> bool:
        next_order = int(
            await self.db.fetch_val(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM priorities"
            )
        )
        try:
            await self.db.execute(
                "INSERT INTO priorities (name, sort_order, is_active) VALUES (?, ?, 1)",
                (name, next_order),
            )
            logger.info("Добавлен приоритет '%s'", name)
            return True
        except Exception:
            return False

    async def rename_priority(self, priority_id: int, new_name: str) -> bool:
        try:
            await self.db.execute(
                "UPDATE priorities SET name = ? WHERE id = ?", (new_name, priority_id)
            )
            return True
        except Exception:
            return False

    async def set_priority_active(self, priority_id: int, is_active: bool) -> None:
        await self.db.execute(
            "UPDATE priorities SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, priority_id),
        )
        logger.info("Приоритет id=%s => is_active=%s", priority_id, is_active)

    # ------------------------------------------------------------------
    # Справочники для экспорта
    # ------------------------------------------------------------------
    async def all_for_export(self) -> dict[str, list[dict[str, Any]]]:
        """Все справочники одним запросом-набором — для листа СПРАВОЧНИКИ."""
        return {
            "categories": await self.list_categories(),
            "statuses": await self.list_statuses(),
            "priorities": await self.list_priorities(),
            "users": await self.db.fetch_all(
                "SELECT id, username, full_name, role, is_active, joined_at "
                "FROM users ORDER BY full_name"
            ),
        }

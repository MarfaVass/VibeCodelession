"""Репозиторий задач: все SQL-запросы к таблицам tasks и task_history.

Репозиторий знает только про хранение данных. Бизнес-правила
(уведомления, история, права доступа) живут в сервисах.
"""

from __future__ import annotations

import logging
from typing import Any

from ..database import Database

logger = logging.getLogger(__name__)


class TaskRepository:
    """CRUD-операции над задачами и историей изменений."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Внутренние помощники
    # ------------------------------------------------------------------
    _SELECT_WITH_JOINS = """
        SELECT t.*,
               c.name AS category,
               p.name AS priority,
               s.name AS status,
               s.is_final AS status_is_final,
               au.full_name AS creator_name,
               bu.full_name AS assignee_name
        FROM tasks t
        JOIN categories c ON c.id = t.category_id
        JOIN priorities p ON p.id = t.priority_id
        JOIN statuses   s ON s.id = t.status_id
        JOIN users au   ON au.id = t.created_by
        LEFT JOIN users bu ON bu.id = t.assigned_to
    """

    # ------------------------------------------------------------------
    # Создание
    # ------------------------------------------------------------------
    async def create(
        self,
        *,
        title: str,
        description: str,
        category_id: int,
        priority_id: int,
        status_id: int,
        created_by: int,
        assigned_to: int | None,
        due_date: str | None,
        now_iso: str,
    ) -> int:
        """Создаёт задачу и первую запись в истории. Возвращает ID задачи."""
        sql = """
            INSERT INTO tasks
                (title, description, category_id, priority_id, status_id,
                 created_by, assigned_to, created_at, updated_at, due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            title, description, category_id, priority_id, status_id,
            created_by, assigned_to, now_iso, now_iso, due_date,
        )
        async with self.db.transaction() as conn:
            cursor = await conn.execute(sql, params)
            task_id = cursor.lastrowid
            await conn.execute(
                """
                INSERT INTO task_history (task_id, user_id, action, old_value, new_value, created_at)
                VALUES (?, ?, 'created', NULL, ?, ?)
                """,
                (task_id, created_by, title, now_iso),
            )
        logger.info("Создана задача id=%s '%s'", task_id, title)
        return int(task_id)

    # ------------------------------------------------------------------
    # Чтение
    # ------------------------------------------------------------------
    async def get(self, task_id: int) -> dict[str, Any] | None:
        """Загружает одну задачу с названиями из справочников."""
        return await self.db.fetch_one(
            self._SELECT_WITH_JOINS + " WHERE t.id = ?", (task_id,)
        )

    async def get_plain(self, task_id: int) -> dict[str, Any] | None:
        """Загружает сырую строку задачи без JOIN (для быстрых проверок)."""
        return await self.db.fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))

    async def count(self) -> int:
        """Общее количество задач."""
        return int(await self.db.fetch_val("SELECT COUNT(*) FROM tasks"))

    # ------------------------------------------------------------------
    # Списки с фильтрацией
    # ------------------------------------------------------------------
    async def list_tasks(
        self,
        *,
        order: str = "asc",
        limit: int = 10,
        offset: int = 0,
        assigned_to: int | None = None,
        created_by: int | None = None,
        category_id: int | None = None,
        status_id: int | None = None,
        priority_id: int | None = None,
        only_overdue: bool = False,
        only_completed: bool = False,
        search_text: str | None = None,
        count_only: bool = False,
    ) -> list[dict[str, Any]] | int:
        """Универсальная выборка задач с фильтрами и пагинацией.

        :param order: 'asc' — от старых к новым (по умолчанию для /list),
                      'desc' — от новых к старым.
        :param count_only: True → возвращает только количество подходящих
                      записей (для расчёта числа страниц).
        Фильтры комбинируются через условия AND.
        """
        where: list[str] = []
        params: list[Any] = []

        if assigned_to is not None:
            where.append("t.assigned_to = ?")
            params.append(assigned_to)
        if created_by is not None:
            where.append("t.created_by = ?")
            params.append(created_by)
        if category_id is not None:
            where.append("t.category_id = ?")
            params.append(category_id)
        if status_id is not None:
            where.append("t.status_id = ?")
            params.append(status_id)
        if priority_id is not None:
            where.append("t.priority_id = ?")
            params.append(priority_id)
        if only_completed:
            where.append("s.is_final = 1 AND s.name != 'Отменена'")
        if only_overdue:
            where.append(
                "t.due_date IS NOT NULL AND t.due_date < datetime('now') "
                "AND s.is_final = 0"
            )
            # Примечание: due_date хранится в ISO UTC, сравнение с datetime('now')
            # корректно посимвольно в формате ISO.
        if search_text:
            # ufold() — SQL-функция Unicode-свёртывания регистра (регистрируется
            # в Database.connect): обычный LIKE не приводит к нижнему регистру
            # кириллицу. Фильтрация выполняется в SQL ДО LIMIT/OFFSET, поэтому
            # пагинация и условие count_only остаются корректными.
            where.append("(ufold(t.title) LIKE ? OR ufold(t.description) LIKE ?)")
            like = f"%{search_text.casefold()}%"
            params.extend([like, like])

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        direction = "ASC" if order == "asc" else "DESC"

        if count_only:
            return int(await self.db.fetch_val(
                "SELECT COUNT(*) FROM tasks t "
                "JOIN statuses s ON s.id = t.status_id" + where_sql,
                tuple(params),
            ))

        sql = self._SELECT_WITH_JOINS + where_sql + \
            f" ORDER BY t.created_at {direction}, t.id {direction} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return await self.db.fetch_all(sql, tuple(params))

    # ------------------------------------------------------------------
    # Изменение
    # ------------------------------------------------------------------
    async def update_field(
        self, task_id: int, column: str, value: Any, now_iso: str
    ) -> None:
        """Обновляет одно поле задачи (только из белого списка имён колонок)."""
        allowed = {"title", "description", "category_id", "priority_id",
                   "status_id", "assigned_to", "due_date", "completed_at"}
        if column not in allowed:
            raise ValueError(f"Недопустимое имя колонки: {column}")
        await self.db.execute(  # nosec — column из белого списка
            f"UPDATE tasks SET {column} = ?, updated_at = ? WHERE id = ?",
            (value, now_iso, task_id),
        )

    async def set_fields(self, fields: dict[str, Any], task_id: int, now_iso: str) -> None:
        """Обновляет несколько полей одной транзакцией."""
        allowed = {"title", "description", "category_id", "priority_id",
                   "status_id", "assigned_to", "due_date", "completed_at"}
        for column in fields:
            if column not in allowed:
                raise ValueError(f"Недопустимое имя колонки: {column}")
        assignments = ", ".join(f"{column} = ?" for column in fields) + ", updated_at = ?"
        params = list(fields.values()) + [now_iso, task_id]
        await self.db.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ?", tuple(params)
        )

    async def delete(self, task_id: int) -> bool:
        """Физически удаляет задачу (история удаляется каскадом).

        Возвращает True, если задача существовала.
        """
        deleted = await self.db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if deleted:
            logger.info("Удалена задача id=%s", task_id)
        return bool(deleted)

    # ------------------------------------------------------------------
    # История
    # ------------------------------------------------------------------
    async def add_history(
        self,
        task_id: int,
        user_id: int,
        action: str,
        old_value: str | None,
        new_value: str | None,
        now_iso: str,
    ) -> None:
        """Добавляет запись в историю изменений задачи."""
        await self.db.execute(
            """
            INSERT INTO task_history (task_id, user_id, action, old_value, new_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, user_id, action, old_value, new_value, now_iso),
        )

    async def get_history(self, task_id: int, limit: int = 20) -> list[dict[str, Any]]:
        """История изменений задачи от последней записи к первой."""
        return await self.db.fetch_all(
            """
            SELECT h.*, u.full_name AS user_name
            FROM task_history h
            LEFT JOIN users u ON u.id = h.user_id
            WHERE h.task_id = ?
            ORDER BY h.id DESC
            LIMIT ?
            """,
            (task_id, limit),
        )

    # ------------------------------------------------------------------
    # Агрегаты для статистики и экспорта
    # ------------------------------------------------------------------
    async def status_counts(self) -> list[dict[str, Any]]:
        """Количество задач по каждому статусу."""
        return await self.db.fetch_all(
            """
            SELECT s.name, COUNT(t.id) AS cnt
            FROM statuses s
            LEFT JOIN tasks t ON t.status_id = s.id
            GROUP BY s.id ORDER BY s.sort_order
            """
        )

    async def overdue_count(self) -> int:
        """Количество просроченных незавершённых задач."""
        return int(await self.db.fetch_val(
            """
            SELECT COUNT(*) FROM tasks t
            JOIN statuses s ON s.id = t.status_id
            WHERE t.due_date IS NOT NULL AND t.due_date < datetime('now')
              AND s.is_final = 0
            """
        ))

    async def category_counts(self) -> list[dict[str, Any]]:
        """Распределение задач по категориям."""
        return await self.db.fetch_all(
            """
            SELECT c.name, COUNT(t.id) AS cnt
            FROM categories c LEFT JOIN tasks t ON t.category_id = c.id
            GROUP BY c.id ORDER BY cnt DESC, c.name
            """
        )

    async def assignee_counts(self) -> list[dict[str, Any]]:
        """Распределение задач по исполнителям (включая «не назначена»)."""
        return await self.db.fetch_all(
            """
            SELECT COALESCE(u.full_name, 'Не назначена') AS name, COUNT(t.id) AS cnt
            FROM tasks t LEFT JOIN users u ON u.id = t.assigned_to
            GROUP BY u.id ORDER BY cnt DESC
            """
        )

    async def priority_counts(self) -> list[dict[str, Any]]:
        """Распределение задач по приоритетам."""
        return await self.db.fetch_all(
            """
            SELECT p.name, COUNT(t.id) AS cnt
            FROM priorities p LEFT JOIN tasks t ON t.priority_id = p.id
            GROUP BY p.id ORDER BY p.sort_order
            """
        )

    async def all_for_export(self) -> list[dict[str, Any]]:
        """Все задачи со справочными названиями — для CSV и Excel."""
        return await self.db.fetch_all(
            self._SELECT_WITH_JOINS + " ORDER BY t.created_at ASC, t.id ASC"
        )

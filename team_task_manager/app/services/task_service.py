"""Сервис задач: бизнес-правила поверх репозитория.

Здесь живут:
  * права доступа (кто что может делать с задачей);
  * правила смены статуса и отметки completed_at;
  * запись истории изменений;
  * формирование карточки задачи для показа в Telegram.

Сервис не знает про aiogram — только про данные.
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from ..database.database import Database
from ..database.repositories.settings import SettingsRepository
from ..database.repositories.tasks import TaskRepository
from ..database.repositories.users import UserRepository
from ..utils.dates import format_datetime, is_overdue, now_utc_iso

logger = logging.getLogger(__name__)

# Разрешённые переходы статусов для MEMBER:
# из завершающих статусов (Выполнена/Отменена) участник менять не может.
PAGE_SIZE = 10


class PermissionDenied(Exception):
    """Пользователь пытается сделать то, что не входит в его роль."""


class TaskService:
    """Оркестрирует операции над задачами."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.tasks = TaskRepository(db)
        self.users = UserRepository(db)
        self.settings = SettingsRepository(db)

    # ------------------------------------------------------------------
    # Права доступа (серверная проверка — вызывается в каждом обработчике)
    # ------------------------------------------------------------------
    @staticmethod
    def is_admin(user: dict[str, Any]) -> bool:
        return user["role"] == "admin"

    def can_view_task(self, user: dict[str, Any], task: dict[str, Any]) -> bool:
        """Активный участник команды видит задачи своей команды."""
        return bool(user["is_active"])

    def can_edit_task(self, user: dict[str, Any], task: dict[str, Any]) -> bool:
        """Редактирование полей: админ — любую, участник — только свою назначенную."""
        if self.is_admin(user):
            return True
        return task["assigned_to"] == user["id"]

    def can_change_status(self, user: dict[str, Any], task: dict[str, Any]) -> bool:
        """Смена статуса: админ — всегда; участник — свою задачу, если она
        ещё не в завершающем статусе."""
        if self.is_admin(user):
            return True
        if task["assigned_to"] != user["id"]:
            return False
        return not task["status_is_final"]

    def can_delete_task(self, user: dict[str, Any], task: dict[str, Any]) -> bool:
        """Удаление разрешено только активным администраторам.

        Проверка is_active — «защита в глубину»: middleware уже блокирует
        неактивных пользователей, но право должно проверяться и в самом
        сервисе, если он вызывается вне потока событий бота.
        """
        return self.is_admin(user) and bool(user["is_active"])

    # ------------------------------------------------------------------
    # Создание и получение
    # ------------------------------------------------------------------
    async def create_task(
        self,
        *,
        title: str,
        description: str,
        category_id: int,
        priority_id: int,
        assigned_to: int | None,
        due_date_iso: str | None,
        user_id: int,
        timezone_name: str,
    ) -> int:
        """Создаёт задачу со статусом «первый активный статус» справочника.

        Уведомление исполнителю отправляет NotificationService (отдельно).
        """
        statuses = await self.settings.list_statuses(only_active=True)
        if not statuses:
            raise RuntimeError("В справочнике нет активных статусов — обратитесь к администратору")
        initial_status = statuses[0]

        task_id = await self.tasks.create(
            title=title,
            description=description,
            category_id=category_id,
            priority_id=priority_id,
            status_id=initial_status["id"],
            created_by=user_id,
            assigned_to=assigned_to,
            due_date=due_date_iso,
            now_iso=now_utc_iso(),
        )
        return task_id

    async def get_task(self, task_id: int) -> dict[str, Any] | None:
        """Задача с названиями справочников."""
        task = await self.tasks.get(task_id)
        if task:
            task["status_is_final"] = bool(task.get("status_is_final"))
        return task

    # ------------------------------------------------------------------
    # Изменения с записью истории
    # ------------------------------------------------------------------
    async def _apply_change(
        self,
        task_id: int,
        user_id: int,
        action: str,
        old_value: str | None,
        new_value: str | None,
        **fields: Any,
    ) -> None:
        """Обновляет поля задачи и записывает историю одной транзакцией."""
        async with self.db.transaction() as conn:
            assignments = ", ".join(f"{k} = ?" for k in fields) + ", updated_at = ?"
            params = [*fields.values(), now_utc_iso(), task_id]
            await conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", tuple(params))
            await conn.execute(
                """
                INSERT INTO task_history (task_id, user_id, action, old_value, new_value, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, user_id, action, old_value, new_value, now_utc_iso()),
            )

    async def change_status(
        self, task_id: int, new_status_id: int, user_id: int
    ) -> dict[str, Any] | None:
        """Смена статуса; при переходе в завершающий ставит completed_at,
        при выходе из завершающего — сбрасывает его."""
        task = await self.get_task(task_id)
        if not task:
            return None
        new_status = await self.settings.get_status(new_status_id)
        if not new_status:
            raise PermissionDenied("Статус не найден")

        old_status_id = task["status_id"]
        changes: dict[str, Any] = {"status_id": new_status_id}
        new_is_final = bool(new_status["is_final"])

        if new_is_final and not task["status_is_final"]:
            changes["completed_at"] = now_utc_iso()
        elif not new_is_final and task["status_is_final"]:
            changes["completed_at"] = None

        await self._apply_change(
            task_id, user_id, "status", task["status"], new_status["name"], **changes
        )
        logger.info("Задача id=%s: статус '%s' -> '%s'", task_id, task["status"], new_status["name"])
        return await self.get_task(task_id)

    async def change_priority(self, task_id: int, new_priority_id: int, user_id: int) -> dict[str, Any] | None:
        task = await self.get_task(task_id)
        if not task:
            return None
        priority = await self.settings.get_priority(new_priority_id)
        if not priority:
            raise PermissionDenied("Приоритет не найден")
        await self._apply_change(
            task_id, user_id, "priority", task["priority"], priority["name"],
            priority_id=new_priority_id,
        )
        return await self.get_task(task_id)

    async def change_assignee(self, task_id: int, assignee_id: int | None, user_id: int) -> dict[str, Any] | None:
        """Назначение исполнителя (None — снять назначение)."""
        task = await self.get_task(task_id)
        if not task:
            return None
        new_name = "не назначена"
        if assignee_id is not None:
            user = await self.users.get(assignee_id)
            if not user or not user["is_active"]:
                raise PermissionDenied("Исполнитель не найден или неактивен")
            new_name = user["full_name"]
        await self._apply_change(
            task_id, user_id, "assignee", task["assignee_name"] or "не назначена",
            new_name, assigned_to=assignee_id,
        )
        return await self.get_task(task_id)

    # Сентинел для различения «не менять дедлайн» и «очистить дедлайн».
    _UNSET = object()

    async def edit_fields(
        self,
        task_id: int,
        user_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        category_id: int | None = None,
        priority_id: int | None = None,
        due_date=_UNSET,
    ) -> dict[str, Any] | None:
        """Редактирование произвольного набора полей с записью истории по каждому.

        :param due_date: _UNSET — не менять; None — очистить дедлайн;
               строка ISO — установить новый срок.
        """
        task = await self.get_task(task_id)
        if not task:
            return None

        updates: dict[str, Any] = {}
        if title is not None and title != task["title"]:
            updates["title"] = title
            await self.tasks.add_history(
                task_id, user_id, "title", task["title"], title, now_utc_iso()
            )
        if description is not None and description != task["description"]:
            updates["description"] = description
            await self.tasks.add_history(
                task_id, user_id, "description", None, "(изменено)", now_utc_iso()
            )
        if category_id is not None and category_id != task["category_id"]:
            cat = await self.settings.get_category(category_id)
            if not cat:
                raise PermissionDenied("Категория не найдена")
            updates["category_id"] = category_id
            await self.tasks.add_history(
                task_id, user_id, "category", task["category"], cat["name"], now_utc_iso()
            )
        if due_date is not self._UNSET:
            updates["due_date"] = due_date
            await self.tasks.add_history(
                task_id, user_id, "due_date", task["due_date"] or "—",
                due_date or "—", now_utc_iso()
            )

        if updates:
            await self.tasks.set_fields(updates, task_id, now_utc_iso())
        return await self.get_task(task_id)

    async def delete_task(self, task_id: int, user_id: int) -> bool:
        """Удаление задачи (только админ — проверка в обработчике)."""
        task = await self.get_task(task_id)
        if not task:
            return False
        deleted = await self.tasks.delete(task_id)
        if deleted:
            # История удаляется каскадно; фиксируем событие в логах.
            logger.info("Задача id=%s ('%s') удалена пользователем id=%s",
                        task_id, task["title"], user_id)
        return deleted

    # ------------------------------------------------------------------
    # Карточка задачи
    # ------------------------------------------------------------------
    def format_task_card(
        self, task: dict[str, Any], timezone_name: str, for_history: bool = False
    ) -> str:
        """Готовит текст карточки задачи для Telegram."""
        overdue_mark = ""
        if is_overdue(task.get("due_date"), bool(task["status_is_final"]), timezone_name):
            overdue_mark = " ⚠️ ПРОСРОЧЕНА"

        lines = [
            f"📋 Задача #{task['id']}{overdue_mark}",
            f"<b>{task['title']}</b>",
            "",
        ]
        if task.get("description"):
            lines.append(f"📝 {task['description']}")
            lines.append("")
        assignee = task.get("assignee_name") or "не назначена"
        lines += [
            f"🗂 Категория: {task['category']}",
            f"⚡ Приоритет: {task['priority']}",
            f"📍 Статус: {task['status']}",
            f"👤 Автор: {task.get('creator_name', '—')}",
            f"🎯 Исполнитель: {assignee}",
            f"📅 Дедлайн: {task.get('due_date') or '—'}",
            f"🕓 Создана: {format_datetime(task['created_at'], timezone_name)}",
            f"🔄 Обновлена: {format_datetime(task['updated_at'], timezone_name)}",
        ]
        if task.get("completed_at"):
            lines.append(f"✅ Завершена: {format_datetime(task['completed_at'], timezone_name)}")
        return "\n".join(lines)

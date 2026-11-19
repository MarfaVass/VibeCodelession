"""Сервис статистики — все показатели рассчитываются напрямую из SQLite.

Никаких демонстрационных/синтетических данных: числа берутся
только из агрегатов по реальным строкам таблицы tasks.

Подсчёт «выполнено» и «отменено» опирается на стандартные статусы:
завершающие (is_final=1) статусы, кроме статуса с именем «Отменена»,
считаются выполненными. Эту семантику важно учитывать при
перенастройке справочника статусов администратором.
"""

from __future__ import annotations

from typing import Any

from ..database.database import Database
from ..database.repositories.settings import SettingsRepository
from ..database.repositories.tasks import TaskRepository

CANCELLED_STATUS_NAME = "Отменена"  # статус, исключаемый из счётчика «выполнено»


class StatisticsService:
    """Компоновка статистики для /stats и листа СВОДКА в Excel."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.tasks = TaskRepository(db)
        self.settings = SettingsRepository(db)

    async def _completed_count(self) -> int:
        """Количество выполненных задач: финальные статусы, кроме «Отменена»."""
        statuses = await self.settings.list_statuses()
        cancelled_ids = tuple(
            s["id"] for s in statuses if s["name"] == CANCELLED_STATUS_NAME
        )
        rows = await self.db.fetch_all(
            """
            SELECT s.name AS name, s.is_final AS is_final, COUNT(t.id) AS cnt
            FROM tasks t JOIN statuses s ON s.id = t.status_id
            GROUP BY s.id
            """
        )
        total = 0
        for row in rows:
            if not row["is_final"]:
                continue
            if cancelled_ids and row["name"] == CANCELLED_STATUS_NAME:
                continue
            total += row["cnt"]
        return total

    async def collect(self) -> dict[str, Any]:
        """Собирает все показатели одним набором (используется и в Excel)."""
        by_status = await self.tasks.status_counts()
        return {
            "total": sum(row["cnt"] for row in by_status),
            "by_status": by_status,
            "completed": await self._completed_count(),
            "overdue": await self.tasks.overdue_count(),
            "by_category": await self.tasks.category_counts(),
            "by_assignee": await self.tasks.assignee_counts(),
            "by_priority": await self.tasks.priority_counts(),
        }

    async def format_text(self) -> str:
        """Готовит текст статистики для команды /stats."""
        stats = await self.collect()
        lines = [
            "📊 <b>Статистика задач</b>",
            f"Всего задач: {stats['total']}",
            "",
            "📍 По статусам:",
        ]
        for row in stats["by_status"]:
            lines.append(f"  • {row['name']}: {row['cnt']}")

        lines += [
            "",
            f"✅ Выполнено: {stats['completed']}",
            f"⚠️ Просрочено: {stats['overdue']}",
            "",
            "🗂 По категориям:",
        ]
        for row in stats["by_category"]:
            lines.append(f"  • {row['name']}: {row['cnt']}")

        lines.append("\n🎯 По исполнителям:")
        for row in stats["by_assignee"]:
            lines.append(f"  • {row['name']}: {row['cnt']}")

        return "\n".join(lines)

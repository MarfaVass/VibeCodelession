"""Модели данных (dataclasses) — компактное представление строк из БД.

Репозитории возвращают словари; сервисы при необходимости
оборачивают их в эти модели для удобной работы с полями.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Task:
    """Задача команды."""

    id: int
    title: str
    description: str
    category_id: int
    priority_id: int
    status_id: int
    created_by: int
    assigned_to: int | None
    created_at: str
    updated_at: str
    due_date: str | None
    completed_at: str | None

    # Развёрнутые названия из справочников (заполняются сервисом)
    category: str = ""
    priority: str = ""
    status: str = ""
    status_is_final: bool = False
    creator_name: str = ""
    assignee_name: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Task":
        return cls(
            id=row["id"],
            title=row["title"],
            description=row.get("description", ""),
            category_id=row["category_id"],
            priority_id=row["priority_id"],
            status_id=row["status_id"],
            created_by=row["created_by"],
            assigned_to=row.get("assigned_to"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            due_date=row.get("due_date"),
            completed_at=row.get("completed_at"),
        )


@dataclass
class User:
    """Участник команды (id = Telegram ID)."""

    id: int
    username: str | None
    full_name: str
    role: str  # 'admin' | 'member'
    is_active: bool
    joined_at: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "User":
        return cls(
            id=row["id"],
            username=row.get("username"),
            full_name=row["full_name"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            joined_at=row["joined_at"],
        )


@dataclass
class ListItem:
    """Элемент справочника (категория, статус или приоритет)."""

    id: int
    name: str
    sort_order: int = 0
    is_final: bool = False
    is_active: bool = True

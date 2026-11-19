"""Общие фикстуры pytest.

ВАЖНО: тесты работают с временной тестовой БД в tmp_path —
никогда с рабочей базой data/tasks.db (это исключено самой
архитектурой фикстур).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database.database import Database
from app.database.migrations import migrate
from app.database.repositories.settings import SettingsRepository
from app.database.repositories.users import UserRepository
from app.services.statistics_service import StatisticsService
from app.services.task_service import TaskService


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    """Свежая тестовая база с применёнными миграциями на каждый тест."""
    database = Database(tmp_path / "test_tasks.db")
    await database.connect()
    await migrate(database)
    yield database
    await database.close()


@pytest.fixture
async def task_service(db: Database) -> TaskService:
    return TaskService(db)


@pytest.fixture
async def users_repo(db: Database) -> UserRepository:
    return UserRepository(db)


@pytest.fixture
async def settings_repo(db: Database) -> SettingsRepository:
    return SettingsRepository(db)


@pytest.fixture
async def statistics_service(db: Database) -> StatisticsService:
    return StatisticsService(db)


@pytest.fixture
async def admin_user(users_repo: UserRepository) -> dict:
    """Администратор команды."""
    await users_repo.ensure_registered(1001, "@admin", "Администратор Тестов")
    await users_repo.set_role(1001, "admin")
    return await users_repo.get(1001)


@pytest.fixture
async def member_user(users_repo: UserRepository) -> dict:
    """Обычный участник команды."""
    await users_repo.ensure_registered(1002, "@member", "Мария Участница")
    return await users_repo.get(1002)


@pytest.fixture
async def sample_task(task_service: TaskService, settings_repo: SettingsRepository,
                      admin_user: dict) -> dict:
    """Одна базовая задача, созданная администратором."""
    categories = await settings_repo.list_categories(only_active=True)
    priorities = await settings_repo.list_priorities(only_active=True)
    task_id = await task_service.create_task(
        title="Тестовая задача",
        description="Описание тестовой задачи",
        category_id=categories[0]["id"],
        priority_id=priorities[0]["id"],
        assigned_to=None,
        due_date_iso=None,
        user_id=admin_user["id"],
        timezone_name="UTC",
    )
    return await task_service.get_task(task_id)

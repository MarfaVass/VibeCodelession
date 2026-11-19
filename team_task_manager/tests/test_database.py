"""Тесты базы данных: создание, миграции, версионирование, устойчивость."""

from __future__ import annotations

import aiosqlite
import pytest

from app.database.database import Database
from app.database.migrations import get_schema_version, migrate
from app.database.repositories.settings import SettingsRepository


async def test_database_created(db: Database, tmp_path) -> None:
    """Файл тестовой БД создан и подключение работает."""
    assert (tmp_path / "test_tasks.db").exists()
    version = await get_schema_version(db)
    assert version == 1


async def test_migration_creates_all_tables(db: Database) -> None:
    """После миграций существуют все таблицы ТЗ."""
    tables = {
        row["name"] for row in await db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    expected = {"users", "categories", "statuses", "priorities",
                "tasks", "task_history", "settings", "notifications"}
    assert expected <= tables


async def test_foreign_keys_enforced(db: Database) -> None:
    """Внешние ключи включены: вставка задачи с чужой категорией падает."""
    with pytest.raises(Exception):
        await db.execute(
            """
            INSERT INTO tasks (title, description, category_id, priority_id, status_id,
                               created_by, created_at, updated_at)
            VALUES ('x', '', 999999, 1, 1, 1001, datetime('now'), datetime('now'))
            """
        )


async def test_migration_idempotent(db: Database) -> None:
    """Повторный вызов migrate не дублирует справочники."""
    await migrate(db)
    repo = SettingsRepository(db)
    assert len(await repo.list_categories()) == 5
    assert len(await repo.list_statuses()) == 5
    assert len(await repo.list_priorities()) == 4


async def test_seed_dictionaries(db: Database) -> None:
    """Базовые значения справочников созданы при миграции."""
    repo = SettingsRepository(db)
    names = [c["name"] for c in await repo.list_categories()]
    assert "Общие" in names and "Проекты" in names
    status_names = [s["name"] for s in await repo.list_statuses()]
    assert status_names[0] == "Новая" and "Выполнена" in status_names
    prio_names = [p["name"] for p in await repo.list_priorities()]
    assert "Критический" in prio_names


async def test_data_survives_reconnect(tmp_path) -> None:
    """Данные сохраняются после закрытия и повторного подключения."""
    db1 = Database(tmp_path / "persist.db")
    await db1.connect()
    await migrate(db1)
    await db1.execute(
        "INSERT INTO settings (key, value) VALUES ('check', 'value123')"
    )
    await db1.close()

    db2 = Database(tmp_path / "persist.db")
    await db2.connect()
    value = await db2.fetch_val("SELECT value FROM settings WHERE key = 'check'")
    await db2.close()
    assert value == "value123"


async def test_transaction_rollback(db: Database) -> None:
    """Ошибка внутри транзакции отменяет все изменения."""
    rows_before = await db.fetch_all("SELECT COUNT(*) AS c FROM settings")
    # UNIQUE-конфликт в SQLite возбуждает sqlite3.IntegrityError
    # (aiosqlite.IntegrityError) — наследник sqlite3.Error, а не RuntimeError.
    with pytest.raises(aiosqlite.IntegrityError):
        async with db.transaction() as conn:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ('rollback_test', '1')"
            )
            # Триггерим ошибку: нарушение ограничения PRIMARY KEY.
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ('rollback_test', '2')"
            )
    key = await db.fetch_val("SELECT value FROM settings WHERE key = 'rollback_test'")
    assert key is None


async def test_wal_journal_enabled(db: Database) -> None:
    """WAL-режим включён — устойчивость к сбоям питания."""
    mode = await db.fetch_val("PRAGMA journal_mode;")
    assert str(mode).lower() == "wal"

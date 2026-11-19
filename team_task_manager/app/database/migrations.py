"""Версионирование структуры БД и миграции.

Механизм:
  * в таблице `settings` хранится ключ SCHEMA_VERSION;
  * список MIGRATIONS упорядочен от версии 1 к текущей;
  * при запуске применяются все миграции, номер которых больше
    записанной версии;
  * каждая миграция выполняется в одной транзакции — либо полностью
    выполняется, либо полностью откатывается.

Первый запуск: SCHEMA_VERSION отсутствует → БД создаётся с нуля и
заполняется базовыми справочниками (категории, статусы, приоритеты).
"""

from __future__ import annotations

import logging

import aiosqlite

from .database import Database

logger = logging.getLogger(__name__)

SCHEMA_VERSION_KEY = "SCHEMA_VERSION"

# ----------------------------------------------------------------------
# Миграция 1 — первоначальная схема (все таблицы, индексы, базовые значения)
# ----------------------------------------------------------------------
V1_STATEMENTS = (
    # --- Пользователи: id = Telegram ID ---
    """
    CREATE TABLE IF NOT EXISTS users (
        id        INTEGER PRIMARY KEY,          -- Telegram ID пользователя
        username  TEXT,
        full_name TEXT NOT NULL,
        role      TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
        is_active INTEGER NOT NULL DEFAULT 1,
        joined_at TEXT NOT NULL
    )
    """,
    # --- Справочник категорий ---
    """
    CREATE TABLE IF NOT EXISTS categories (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        is_active INTEGER NOT NULL DEFAULT 1
    )
    """,
    # --- Справочник статусов: is_final=True значит задача завершена/отменена ---
    """
    CREATE TABLE IF NOT EXISTS statuses (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
        sort_order INTEGER NOT NULL DEFAULT 0,
        is_final   INTEGER NOT NULL DEFAULT 0,
        is_active  INTEGER NOT NULL DEFAULT 1
    )
    """,
    # --- Справочник приоритетов ---
    """
    CREATE TABLE IF NOT EXISTS priorities (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
        sort_order INTEGER NOT NULL DEFAULT 0,
        is_active  INTEGER NOT NULL DEFAULT 1
    )
    """,
    # --- Задачи ---
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        title        TEXT NOT NULL,
        description  TEXT NOT NULL DEFAULT '',
        category_id  INTEGER NOT NULL REFERENCES categories(id),
        priority_id  INTEGER NOT NULL REFERENCES priorities(id),
        status_id    INTEGER NOT NULL REFERENCES statuses(id),
        created_by   INTEGER NOT NULL REFERENCES users(id),
        assigned_to  INTEGER REFERENCES users(id),
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL,
        due_date     TEXT,
        completed_at TEXT
    )
    """,
    # --- История изменений задач ---
    """
    CREATE TABLE IF NOT EXISTS task_history (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id   INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        user_id   INTEGER NOT NULL REFERENCES users(id),
        action    TEXT NOT NULL,   -- created / status / priority / assignee / edit / delete и т.п.
        old_value TEXT,
        new_value TEXT,
        created_at TEXT NOT NULL
    )
    """,
    # --- Ключ-значение настроек (в т.ч. SCHEMA_VERSION) ---
    """
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """,
    # --- Журнал отправленных уведомлений для защиты от повторов ---
    """
    CREATE TABLE IF NOT EXISTS notifications (
        event_key TEXT PRIMARY KEY,   -- уникальный ключ события, например 'assign:42'
        created_at TEXT NOT NULL
    )
    """,
    # --- Индексы для частых запросов ---
    "CREATE INDEX IF NOT EXISTS idx_tasks_status    ON tasks(status_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_category  ON tasks(category_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_priority  ON tasks(priority_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_assigned  ON tasks(assigned_to)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON tasks(created_by)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_due_date  ON tasks(due_date)",
    "CREATE INDEX IF NOT EXISTS idx_history_task    ON task_history(task_id)",
    # --- Базовые справочники ---
    """
    INSERT OR IGNORE INTO categories (name, is_active) VALUES
        ('Общие', 1), ('Административные', 1), ('Проекты', 1),
        ('Операционные', 1), ('Прочее', 1)
    """,
    """
    INSERT OR IGNORE INTO statuses (name, sort_order, is_final, is_active) VALUES
        ('Новая',       1, 0, 1),
        ('В работе',    2, 0, 1),
        ('На проверке', 3, 0, 1),
        ('Выполнена',   4, 1, 1),
        ('Отменена',    5, 1, 1)
    """,
    """
    INSERT OR IGNORE INTO priorities (name, sort_order, is_active) VALUES
        ('Низкий', 1, 1), ('Обычный', 2, 1), ('Высокий', 3, 1), ('Критический', 4, 1)
    """,
)

# Список миграций: (номер версии, кортеж SQL-команд)
MIGRATIONS: list[tuple[int, tuple[str, ...]]] = [
    (1, V1_STATEMENTS),
]


async def get_schema_version(db: Database) -> int:
    """Читает текущую версию схемы (0 — база ещё не создана).

    На совершенно свежей базе таблицы settings ещё нет — это
    нормальная ситуация, означающая версию 0.
    """
    try:
        version = await db.fetch_val(
            "SELECT value FROM settings WHERE key = ?", (SCHEMA_VERSION_KEY,)
        )
    except aiosqlite.OperationalError:
        return 0  # таблицы settings ещё не существует
    return int(version) if version else 0


async def migrate(db: Database) -> int:
    """Приводит базу к актуальной версии схемы. Возвращает текущую версию.

    Перед применением миграции автоматически создаётся резервная копия,
    если включён BackupService (вызов осуществляется из main).
    """
    current = await get_schema_version(db)

    # Свежая БД: создаём всё сразу через миграцию 1.
    if current == 0:
        logger.info("База данных не найдена — создаю структуру с нуля")
    elif current < len(MIGRATIONS):
        logger.info("Требуется миграция БД: v%d -> v%d", current, len(MIGRATIONS))

    for version, statements in MIGRATIONS:
        if version <= current:
            continue
        logger.info("Применяю миграцию v%d (%d команд SQL)", version, len(statements))
        async with db.transaction() as conn:
            for sql in statements:
                await conn.execute(sql)
            await conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (SCHEMA_VERSION_KEY, str(version)),
            )
    return len(MIGRATIONS)


async def ensure_empty_settings(db: Database) -> None:
    """Гарантирует существование таблицы настроек даже без миграций (для тестов)."""
    await db.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
    )

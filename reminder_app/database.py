import sqlite3
from datetime import datetime
from pathlib import Path

# Путь к базе данных внутри папки приложения.
DB_PATH = Path(__file__).resolve().parent / "reminders.db"


def get_connection():
    """Создает соединение с базой данных."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    """Создает таблицу напоминаний, если ее еще нет."""
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                remind_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Ожидает',
                repeat_minutes INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """)


def add_reminder(title, description, remind_at, repeat_minutes=0):
    """Добавляет новое напоминание."""
    title = title.strip()

    if not title:
        raise ValueError("Название напоминания не может быть пустым.")

    if repeat_minutes < 0:
        raise ValueError("Интервал повторения не может быть отрицательным.")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO reminders
                (title, description, remind_at, repeat_minutes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                title,
                description.strip(),
                remind_at,
                repeat_minutes,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return cursor.lastrowid


def get_reminders(status=None):
    """Возвращает напоминания; при необходимости фильтрует по статусу."""
    with get_connection() as connection:
        if status and status != "Все":
            rows = connection.execute(
                """
                SELECT * FROM reminders
                WHERE status = ?
                ORDER BY remind_at
                """,
                (status,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM reminders ORDER BY remind_at"
            ).fetchall()

    return [dict(row) for row in rows]


def update_status(reminder_id, status):
    """Изменяет статус напоминания."""
    allowed_statuses = {
        "Ожидает",
        "Готово",
        "Просрочено",
        "Отменено",
    }

    if status not in allowed_statuses:
        raise ValueError(f"Неизвестный статус: {status}")

    with get_connection() as connection:
        connection.execute(
            "UPDATE reminders SET status = ? WHERE id = ?",
            (status, reminder_id),
        )


def delete_reminder(reminder_id):
    """Удаляет напоминание по его идентификатору."""
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM reminders WHERE id = ?",
            (reminder_id,),
        )


def mark_overdue():
    """Помечает просроченные напоминания, которые еще ожидают выполнения."""
    now = datetime.now().isoformat(timespec="seconds")

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE reminders
            SET status = 'Просрочено'
            WHERE status = 'Ожидает'
              AND remind_at < ?
              AND repeat_minutes = 0
            """,
            (now,),
        )

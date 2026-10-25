import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "reminders.db"

STATUSES = {"Ожидает", "Готово", "Отменено"}


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    """Создает таблицы задач и расписания уведомлений."""
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                remind_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Ожидает',
                created_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS reminder_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reminder_id INTEGER NOT NULL,
                event_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Ожидает',
                FOREIGN KEY (reminder_id)
                    REFERENCES reminders(id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_due
            ON reminder_events(status, event_at)
        """)


def add_reminder(title, description, remind_at, event_times):
    """Создает задачу и расписание ее уведомлений."""
    title = title.strip()

    if not title:
        raise ValueError("Название напоминания не может быть пустым.")

    if not event_times:
        raise ValueError("Выбери хотя бы одно время напоминания.")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO reminders (title, description, remind_at, created_at)
            VALUES (?, ?, ?, ?)
        """,
            (
                title,
                description.strip(),
                remind_at,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

        reminder_id = cursor.lastrowid

        connection.executemany(
            """
            INSERT INTO reminder_events
                (reminder_id, event_at, event_type)
            VALUES (?, ?, ?)
        """,
            [
                (reminder_id, event_at, event_type)
                for event_at, event_type in event_times
            ],
        )

        return reminder_id


def get_reminders(status=None):
    """Возвращает задачи с количеством ожидающих уведомлений."""
    with get_connection() as connection:
        if status and status != "Все":
            rows = connection.execute(
                """
                SELECT r.*,
                    (SELECT COUNT(*) FROM reminder_events e
                     WHERE e.reminder_id = r.id
                       AND e.status = 'Ожидает') AS pending_events
                FROM reminders r
                WHERE r.status = ?
                ORDER BY r.remind_at
            """,
                (status,),
            ).fetchall()
        else:
            rows = connection.execute("""
                SELECT r.*,
                    (SELECT COUNT(*) FROM reminder_events e
                     WHERE e.reminder_id = r.id
                       AND e.status = 'Ожидает') AS pending_events
                FROM reminders r
                ORDER BY r.remind_at
            """).fetchall()

    return [dict(row) for row in rows]


def get_due_events(now):
    """Получает все уведомления, срок которых уже наступил."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT e.id AS event_id, e.event_at, e.event_type,
                   r.id AS reminder_id, r.title, r.description, r.remind_at
            FROM reminder_events e
            JOIN reminders r ON r.id = e.reminder_id
            WHERE e.status = 'Ожидает'
              AND e.event_at <= ?
              AND r.status = 'Ожидает'
            ORDER BY e.event_at, r.id
        """,
            (now,),
        ).fetchall()

    return [dict(row) for row in rows]


def complete_event(event_id):
    """Отмечает уведомление обработанным."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE reminder_events
            SET status = 'Обработано'
            WHERE id = ?
        """,
            (event_id,),
        )


def complete_reminder(reminder_id):
    """Завершает задачу и отменяет все ее оставшиеся уведомления."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE reminders SET status = 'Готово' WHERE id = ?
        """,
            (reminder_id,),
        )
        connection.execute(
            """
            UPDATE reminder_events
            SET status = 'Отменено'
            WHERE reminder_id = ? AND status = 'Ожидает'
        """,
            (reminder_id,),
        )


def postpone_event(event_id, new_time):
    """Переносит выбранное уведомление на новое время."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE reminder_events
            SET event_at = ?, event_type = 'Отложено', status = 'Ожидает'
            WHERE id = ?
        """,
            (new_time, event_id),
        )


def change_status(reminder_id, status):
    if status not in STATUSES:
        raise ValueError(f"Неизвестный статус: {status}")

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE reminders SET status = ? WHERE id = ?
        """,
            (status, reminder_id),
        )

        if status in {"Готово", "Отменено"}:
            connection.execute(
                """
                UPDATE reminder_events SET status = 'Отменено'
                WHERE reminder_id = ? AND status = 'Ожидает'
            """,
                (reminder_id,),
            )


def delete_reminder(reminder_id):
    with get_connection() as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "DELETE FROM reminder_events WHERE reminder_id = ?",
            (reminder_id,),
        )
        connection.execute(
            "DELETE FROM reminders WHERE id = ?",
            (reminder_id,),
        )

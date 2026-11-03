"""Модуль хранения предварительных заявок в SQLite.

База данных и таблица создаются автоматически при первом обращении.
Используется стандартный модуль :mod:`sqlite3`, одно соединение на операцию.

Каждая заявка — *предварительное обращение* клиента Академии, требующее
последующей обработки представителем Академии (статус ``preliminary``).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Статусы заявки
STATUS_PRELIMINARY = "preliminary"  # предварительное обращение, ждёт обработки
STATUS_PROCESSED = "processed"  # обработано представителем Академии
STATUS_CANCELLED = "cancelled"  # отменено пользователем

VALID_STATUS = (STATUS_PRELIMINARY, STATUS_PROCESSED, STATUS_CANCELLED)

# Категории обращений (совпадают с категориями базы знаний)
CATEGORIES = ("specialist", "club", "international", "client")


@dataclass(frozen=True)
class BookingRecord:
    """Одна предварительная заявка."""

    id: int | None
    vk_id: int
    category: str
    name: str
    contact: str
    request_text: str = ""
    details: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    status: str = STATUS_PRELIMINARY


class BookingDatabase:
    """Обёртка над SQLite для таблицы заявок."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------ #
    #  Схема                                                             #
    # ------------------------------------------------------------------ #

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bookings (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    vk_id        INTEGER NOT NULL,
                    category     TEXT    NOT NULL,
                    name         TEXT    NOT NULL,
                    contact      TEXT    NOT NULL,
                    request_text TEXT    NOT NULL DEFAULT '',
                    details      TEXT    NOT NULL DEFAULT '{}',
                    created_at   TEXT    NOT NULL,
                    status       TEXT    NOT NULL DEFAULT 'preliminary'
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Открыть соединение, гарантируя commit/rollback и закрытие."""

        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    #  Запись заявки                                                     #
    # ------------------------------------------------------------------ #

    def save_booking(
        self,
        vk_id: int,
        category: str,
        name: str,
        contact: str,
        request_text: str = "",
        details: dict[str, str] | None = None,
    ) -> BookingRecord:
        """Сохранить новую заявку и вернуть её запись.

        Обязательные поля: категория, имя, контакт. Остальные — по желанию
        клиента: предварительную заявку можно принять и без них.
        """

        if category not in CATEGORIES:
            raise ValueError(f"Неизвестная категория заявки: {category}")
        name = (name or "").strip()
        contact = (contact or "").strip()
        if not name:
            raise ValueError("Не заполнено обязательное поле: name")
        if not contact:
            raise ValueError("Не заполнено обязательное поле: contact")

        details_json = json.dumps(details or {}, ensure_ascii=False)
        created_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO bookings
                    (vk_id, category, name, contact, request_text, details,
                     created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (int(vk_id), category, name, contact, (request_text or "").strip(),
                 details_json, created_at, STATUS_PRELIMINARY),
            )
            booking_id = cursor.lastrowid
        return BookingRecord(
            id=booking_id,
            vk_id=int(vk_id),
            category=category,
            name=name,
            contact=contact,
            request_text=(request_text or "").strip(),
            details=dict(details or {}),
            created_at=created_at,
            status=STATUS_PRELIMINARY,
        )

    def get_booking(self, booking_id: int) -> BookingRecord | None:
        """Получить заявку по идентификатору (для проверки и тестов)."""

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE id = ?", (booking_id,)
            ).fetchone()
        return self._row_to_record(row)

    def get_latest_booking(self, vk_id: int) -> BookingRecord | None:
        """Последняя заявка пользователя (например, при повторном обращении)."""

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE vk_id = ? ORDER BY id DESC LIMIT 1",
                (int(vk_id),),
            ).fetchone()
        return self._row_to_record(row)

    def set_status(self, booking_id: int, status: str) -> bool:
        """Изменить статус заявки. Возвращает True, если заявка найдена."""

        if status not in VALID_STATUS:
            raise ValueError(f"Неизвестный статус: {status}")
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id)
            )
        return cursor.rowcount > 0

    def count_bookings(self) -> int:
        """Число всех заявок (для диагностики)."""

        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM bookings").fetchone()
        return int(row["n"])

    # ------------------------------------------------------------------ #
    #  Служебное                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _row_to_record(row: sqlite3.Row | None) -> BookingRecord | None:
        if row is None:
            return None
        try:
            details = json.loads(row["details"])
        except (ValueError, TypeError):
            details = {}
        return BookingRecord(
            id=row["id"],
            vk_id=row["vk_id"],
            category=row["category"],
            name=row["name"],
            contact=row["contact"],
            request_text=row["request_text"],
            details=details if isinstance(details, dict) else {},
            created_at=row["created_at"],
            status=row["status"],
        )
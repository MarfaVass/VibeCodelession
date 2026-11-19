"""Ядро работы с базой данных SQLite (асинхронно, через aiosqlite).

Database — единственная точка доступа к соединению с БД.
Все запросы к данным идут через репозитории, которые используют
этот класс. Репозитории никогда не открывают соединения сами.

Внешние ключи включаются для каждого соединения (PRAGMA foreign_keys=ON),
поскольку aiosqlite по умолчанию их отключает.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


def _unicode_casefold(value):
    """SQL-функция ufold(value): Unicode-регистронезависимое свёртывание.

    Встроенный LIKE в SQLite сворачивает регистр только для ASCII-символов,
    поэтому 'договор' не находил 'Договор аренды'. Функция использует
    str.casefold(), который работает для кириллицы и любых остальных
    алфавитов. Не-строковые значения (NULL, числа) возвращаем как есть.
    """
    return value.casefold() if isinstance(value, str) else value


class Database:
    """Обёртка над aiosqlite с транзакциями и удобными fetch-методами."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Жизненный цикл соединения
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        """Открывает соединение и проверяет/создаёт каталог БД."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self._conn is not None:
            return  # уже подключены (защита от повторного вызова)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        # Включаем внешние ключи и WAL-режим (устойчивость к сбоям).
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        # Регистрируем SQL-функцию ufold() для Unicode-регистронезависимого
        # поиска (см. docstring _unicode_casefold). deterministic=True —
        # функция всегда возвращает одинаковый результат для одинакового
        # входа, это позволяет SQLite использовать её безопасно в запросах.
        await self._conn.create_function(
            "ufold", 1, _unicode_casefold, deterministic=True
        )
        logger.info("Подключение к БД установлено: %s", self.db_path)

    async def close(self) -> None:
        """Корректно закрывает соединение."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("Подключение к БД закрыто")

    @property
    def conn(self) -> aiosqlite.Connection:
        """Текущее соединение. Перед использованием обязательно вызвать connect()."""
        if self._conn is None:
            raise RuntimeError("База данных не подключена: сначала вызовите connect()")
        return self._conn

    # ------------------------------------------------------------------
    # Чтение
    # ------------------------------------------------------------------
    async def fetch_all(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        """Возвращает все строки запроса как список словарей."""
        async with self.conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def fetch_one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        """Возвращает одну строку запроса или None."""
        async with self.conn.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row is not None else None

    async def fetch_val(self, sql: str, params: tuple | dict = ()) -> Any:
        """Возвращает первое значение первой строки (например COUNT(*)) или None."""
        async with self.conn.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return row[0] if row is not None else None

    # ------------------------------------------------------------------
    # Запись (с транзакциями)
    # ------------------------------------------------------------------
    async def execute(self, sql: str, params: tuple | dict = ()) -> int:
        """Выполняет одиночный запрос на запись и коммитит.

        Возвращает lastrowid (для INSERT) либо число изменённых строк.
        """
        async with self.conn.execute(sql, params) as cursor:
            await self.conn.commit()
            return cursor.lastrowid if cursor.lastrowid else cursor.rowcount

    async def execute_many(self, sql: str, seq: list[tuple]) -> None:
        """Выполняет один SQL для набора параметров одной транзакцией."""
        await self.conn.executemany(sql, seq)
        await self.conn.commit()

    def transaction(self):
        """Контекстный менеджер транзакции: commit при успехе, rollback при ошибке.

        Использование:
            async with db.transaction() as conn:
                await conn.execute(...)
        """
        return _Transaction(self.conn)


class _Transaction:
    """Контекстный менеджер транзакции поверх существующего соединения."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def __aenter__(self) -> aiosqlite.Connection:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            await self._conn.commit()
        else:
            await self._conn.rollback()
            logger.error("Транзакция откатилась из-за ошибки: %s", exc)
        return False  # исключение пробрасывается дальше


# ----------------------------------------------------------------------
# Единственный экземпляр БД для всего приложения.
# Тесты создают собственный экземпляр Database на тестовом файле.
# ----------------------------------------------------------------------
db = Database("data/tasks.db")

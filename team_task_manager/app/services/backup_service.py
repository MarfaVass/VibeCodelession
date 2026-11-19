"""Резервное копирование базы данных штатным механизмом SQLite.

SQLite backup API (source.backup(destination)) делает согласованную
копию даже во время работы с базой — без блокировки основного соединения.

Правила из ТЗ:
  * копия создаётся при первом запуске, если её ещё нет;
  * копия создаётся перед потенциально опасными операциями;
  * количество хранимых копий ограничено (самые старые удаляются);
  * при ошибке резервного копирования основная БД не затрагивается.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

MAX_BACKUPS = 15  # максимум хранимых резервных копий


class BackupService:
    """Управление резервными копиями SQLite."""

    def __init__(self, db_path: Path, backups_dir: Path) -> None:
        self.db_path = Path(db_path)
        self.backups_dir = Path(backups_dir)

    def _backup_path(self, moment: datetime) -> Path:
        """Имя файла копии: backups/backup_2026-11-19_14-30-05.db."""
        stamp = moment.strftime("%Y-%m-%d_%H-%M-%S")
        return self.backups_dir / f"backup_{stamp}.db"

    async def create_backup(self, source_conn: aiosqlite.Connection, reason: str) -> Path | None:
        """Создаёт резервную копию через штатный SQLite backup API.

        :param source_conn: открытое соединение с основной БД (self.db.conn).
        :param reason: причина создания (старт/миграция/удаление) — только для логов.
        """
        try:
            moment = datetime.now(tz=timezone.utc)
            target_path = self._backup_path(moment)
            self.backups_dir.mkdir(parents=True, exist_ok=True)

            # Имя должно быть уникальным даже при нескольких копиях за секунду.
            counter = 1
            while target_path.exists():
                target_path = self._backup_path(moment).with_name(
                    self._backup_path(moment).stem + f"_{counter}.db"
                )
                counter += 1

            async with aiosqlite.connect(target_path) as destination:
                await source_conn.backup(destination)

            logger.info("Резервная копия создана (%s): %s", reason, target_path.name)
            await self._prune_old_backups()
            return target_path
        except Exception:
            # Крайне важно: ошибка бэкапа не должна ломать основную операцию.
            logger.exception("Не удалось создать резервную копию (%s)", reason)
            return None

    async def _prune_old_backups(self) -> None:
        """Оставляет только последние MAX_BACKUPS копий, старые удаляет."""
        backups = sorted(self.backups_dir.glob("backup_*.db"))
        for stale in backups[:-MAX_BACKUPS]:
            try:
                stale.unlink()
                logger.info("Удалена старая резервная копия: %s", stale.name)
            except OSError:
                logger.warning("Не удалось удалить копию %s", stale.name)

    async def ensure_startup_backup(self, source_conn: aiosqlite.Connection) -> None:
        """Создаёт копию при первом запуске, если её ещё нет.

        По ТЗ «создавать резервную копию при первом запуске, если её еще нет» —
        проверяем наличие хотя бы одного файла backup_*.db.
        """
        has_any = any(self.backups_dir.glob("backup_*.db"))
        if has_any:
            logger.debug("Резервные копии уже существуют — стартовый бэкап не нужен")
            return
        await self.create_backup(source_conn, "первый запуск")

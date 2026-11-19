"""Экспорт задач в CSV.

Требования ТЗ:
  * кодировка UTF-8 с BOM — Excel открывает файл без кракозябр;
  * разделитель ';' — стандарт для русскоязычных табличных редакторов;
  * русскоязычные заголовки;
  * корректная обработка дат и пустых значений.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CSV_HEADERS = [
    "ID", "Название", "Описание", "Категория", "Приоритет", "Статус",
    "Автор", "Ответственный", "Дата создания", "Дедлайн",
    "Дата обновления", "Дата завершения",
]


def _safe(value: Any) -> str:
    """Приводит пустые значения к безопасному виду для CSV."""
    return "" if value is None else str(value)


def build_csv(tasks: list[dict[str, Any]], timezone_name: str) -> str:
    """Формирует содержимое CSV как строку (с BOM, ';' как разделитель)."""
    from ..utils.dates import format_datetime  # noqa: PLC0415 — короткий локальный импорт

    lines = [";".join(CSV_HEADERS)]
    for task in tasks:
        row = [
            task["id"],
            _safe(task["title"]),
            _safe(task["description"]),
            _safe(task["category"]),
            _safe(task["priority"]),
            _safe(task["status"]),
            _safe(task["creator_name"]),
            _safe(task["assignee_name"]),
            format_datetime(task["created_at"], timezone_name),
            format_datetime(task.get("due_date"), timezone_name)
            if task.get("due_date") else "",
            format_datetime(task["updated_at"], timezone_name),
            format_datetime(task.get("completed_at"), timezone_name)
            if task.get("completed_at") else "",
        ]
        # Экранируем значения по правилам CSV (внутри кавычек '""').
        cells = []
        for cell in row:
            cell_text = _safe(cell)
            if ";" in cell_text or '"' in cell_text or "\n" in cell_text:
                cell_text = '"' + cell_text.replace('"', '""') + '"'
            cells.append(cell_text)
        lines.append(";".join(cells))
    return "\n".join(lines) + "\n"


def export_filename() -> str:
    """Имя файла с датой и временем создания: tasks_2026-11-19_14-30.csv."""
    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H-%M")
    return f"tasks_{stamp}.csv"


def write_csv_file(tasks: list[dict[str, Any]], exports_dir: Path, timezone_name: str) -> Path:
    """Записывает CSV в каталог экспорта и возвращает путь к файлу."""
    exports_dir.mkdir(parents=True, exist_ok=True)
    path = exports_dir / export_filename()
    content = build_csv(tasks, timezone_name)
    # encoding='utf-8-sig' добавляет BOM автоматически (см. комментарий ниже).
    path.write_text(content, encoding="utf-8-sig")
    logger.info("CSV-экспорт создан: %s (%d задач)", path.name, len(tasks))
    return path

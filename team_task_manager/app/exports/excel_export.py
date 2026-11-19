"""Экспорт задач в Excel (XLSX) через openpyxl.

Книга состоит из трёх листов:
  1. ЗАДАЧИ       — все задачи с цветовой индикацией статусов и
                    приоритетов, автофильтром, закреплением шапки;
  2. СВОДКА       — итоги: всего/по статусам/просрочено/выполнено и
                    распределения по категориям, исполнителям,
                    приоритетам (часть значений — живые формулы COUNTIF);
  3. СПРАВОЧНИКИ  — категории, статусы, приоритеты, участники команды.

Экспорт — это снимок базы на момент выгрузки: изменения в Excel
никогда не возвращаются в SQLite автоматически.
Образование выпадающих списков (data validation) для справочных
колонок листа ЗАДАЧИ.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from ..utils.dates import get_local_tz, utc_to_local

logger = logging.getLogger(__name__)


def _local_naive(iso_utc: str | None, timezone_name: str) -> datetime | None:
    """datetime в поясе TIMEZONE без tzinfo — так принимает openpyxl.

    Excel не поддерживает часовые пояса в datetime ('Excel does not
    support timezones in datetimes'), поэтому сначала переводим момент
    из UTC в локальное время пользователя, а затем снимаем tzinfo —
    «настенные» значения часов при этом сохраняются.
    """
    local = utc_to_local(iso_utc, timezone_name)
    return local.replace(tzinfo=None) if local is not None else None

# ----------------------------------------------------------------------
# Палитра оформления (нейтральные корпоративные цвета)
# ----------------------------------------------------------------------
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
SECTION_FILL = PatternFill("solid", fgColor="D9E2F3")
THIN_GRAY = Side(style="thin", color="D0D0D0")
BORDER_ALL = Border(left=THIN_GRAY, right=THIN_GRAY, top=THIN_GRAY, bottom=THIN_GRAY)

# Цветовые индикации по ИЗВЕСТНЫМ ключевым словам статусов/приоритетов.
# Справочники настраиваемые: неизвестные названия остаются белыми —
# это осознанное поведение, а не баг (см. README).
STATUS_COLORS = {
    "новая": "FFF2CC",        # жёлтый
    "в работе": "DDEBF7",     # голубой
    "на проверке": "E4DFEC",  # сиреневый
    "выполнена": "E2EFDA",    # зелёный
    "отменена": "F2F2F2",     # серый
}
PRIORITY_COLORS = {
    "критический": "F8CBAD",  # красноватый
    "высокий": "FFE699",      # оранжеватый
    "обычный": "FFFFFF",      # нет окраски
    "низкий": "F2F2F2",       # серый
}

TASK_HEADERS = [
    "ID", "Название", "Описание", "Категория", "Приоритет", "Статус",
    "Автор", "Ответственный", "Дата создания", "Дедлайн",
    "Дата обновления", "Дата завершения",
]


def _status_color(name: str) -> str | None:
    return STATUS_COLORS.get(name.strip().lower())


def _priority_color(name: str) -> str | None:
    return PRIORITY_COLORS.get(name.strip().lower())


def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


# ----------------------------------------------------------------------
# Лист 1 — ЗАДАЧИ
# ----------------------------------------------------------------------
def _sheet_tasks(wb: Workbook, tasks: list[dict[str, Any]], timezone_name: str,
                 dictionaries: dict[str, list[dict[str, Any]]]) -> None:
    ws = wb.active
    ws.title = "ЗАДАЧИ"

    ws.append(TASK_HEADERS)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_index, task in enumerate(tasks, start=2):
        dt_created = _local_naive(task["created_at"], timezone_name)
        dt_due = _local_naive(task.get("due_date"), timezone_name)
        dt_updated = _local_naive(task["updated_at"], timezone_name)
        dt_completed = _local_naive(task.get("completed_at"), timezone_name)

        ws.append([
            task["id"],
            task["title"],
            task.get("description") or "",
            task["category"],
            task["priority"],
            task["status"],
            task["creator_name"],
            task.get("assignee_name") or "Не назначена",
            dt_created,
            dt_due,
            dt_updated,
            dt_completed,
        ])
        # Формат даты и выравнивание текста.
        for col, fmt in ((9, "DD.MM.YYYY HH:MM"), (10, "DD.MM.YYYY"),
                         (11, "DD.MM.YYYY HH:MM"), (12, "DD.MM.YYYY HH:MM")):
            ws.cell(row=row_index, column=col).number_format = fmt
        ws.cell(row=row_index, column=2).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row=row_index, column=3).alignment = Alignment(wrap_text=True, vertical="top")

        # Цветовая индикация статуса (колонка 6) и приоритета (колонка 5).
        # _status_color/_priority_color возвращают строку-HEX — её нужно
        # обернуть в PatternFill (через _fill), иначе openpyxl отбрасывает
        # значение с TypeError: expected <class '...fills.Fill'>.
        status_hex = _status_color(task["status"])
        priority_hex = _priority_color(task["priority"])
        if status_hex:
            ws.cell(row=row_index, column=6).fill = _fill(status_hex)
        if priority_hex:
            ws.cell(row=row_index, column=5).fill = _fill(priority_hex)

        # Просроченная незавершённая задача — красная заливка дедлайна.
        # dt_* naive, поэтому и «сейчас» берём как naive время в том же
        # поясе TIMEZONE из конфигурации — сравнение корректно даже когда
        # пояс сервера не совпадает с поясом команды.
        if task.get("due_date") and not task["status_is_final"] and dt_due:
            if dt_due < datetime.now(get_local_tz(timezone_name)).replace(tzinfo=None):
                ws.cell(row=row_index, column=10).fill = _fill("FFC7CE")
                ws.cell(row=row_index, column=10).font = Font(bold=True, color="9C0006")

    _finish_table(ws, widths=[6, 38, 46, 16, 14, 14, 20, 20, 18, 12, 18, 18])

    # Выпадающие списки для справочных колонок:
    # D — Категория, E — Приоритет, F — Статус.
    last_row = max(len(tasks) + 1, 100)
    _add_dropdown(ws, "D2:D%d" % last_row, "Категории", dictionaries)
    _add_dropdown(ws, "E2:E%d" % last_row, "Приоритеты", dictionaries)
    _add_dropdown(ws, "F2:F%d" % last_row, "Статусы", dictionaries)


def _add_dropdown(ws, target_range: str, section: str,
                  dictionaries: dict[str, list[dict[str, Any]]]) -> None:
    """Data validation: выпадающий список со значениями справочника."""
    try:
        section_map = {"Категории": "categories", "Статусы": "statuses",
                       "Приоритеты": "priorities"}
        rows = dictionaries.get(section_map[section], [])
        values = ",".join(str(r["name"]) for r in rows)[:246]  # лимит openpyxl
        if not values:
            return
        dv = DataValidation(type="list", formula1=f'"{values}"', allow_blank=True)
        dv.error = "Выберите значение из списка"
        dv.errorTitle = "Недопустимое значение"
        ws.add_data_validation(dv)
        dv.add(target_range)
    except Exception as exc:
        logger.warning("Не удалось добавить выпадающий список '%s': %s", section, exc)


def _finish_table(ws, widths: list[int]) -> None:
    """Автофильтр, закрепление шапки, ширины колонок, рамки."""
    last_col = len(widths)
    max_row = ws.max_row or 1
    ws.auto_filter.ref = f"A1:{get_column_letter(last_col)}{max_row}"
    ws.freeze_panes = "A2"
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width
    for row in ws.iter_rows(min_row=2, max_row=max_row, max_col=last_col):
        for cell in row:
            cell.border = BORDER_ALL


# ----------------------------------------------------------------------
# Лист 2 — СВОДКА
# ----------------------------------------------------------------------
def _sheet_summary(wb: Workbook, tasks: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    ws = wb.create_sheet("СВОДКА")

    def section(row: int, title: str) -> None:
        ws.cell(row=row, column=1, value=title).fill = SECTION_FILL
        ws.cell(row=row, column=1).font = Font(bold=True)

    # --- Общие показатели ---
    ws["A1"] = "СВОДКА ПО ЗАДАЧАМ"
    ws["A1"].font = Font(bold=True, size=14)
    row = 3
    section(row, "Общие показатели")
    row += 1
    # «Всего задач» — живая формула по листу ЗАДАЧИ; остальное —
    # расчетные показатели из статистики БД.
    ws.cell(row=row, column=1, value="Всего задач")
    ws.cell(row=row, column=2, value=f"=COUNTA(ЗАДАЧИ!A2:A{max(len(tasks) + 1, 2)})")
    ws.cell(row=row, column=3, value="(формула по листу ЗАДАЧИ)")

    for label, value, comment in [
        ("Выполнено", stats["completed"], ""),
        ("Просрочено", stats["overdue"], "не завершено, дедлайн истёк"),
    ]:
        row += 1
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=2, value=value)
        if comment:
            ws.cell(row=row, column=3, value=comment)
    row += 2

    # --- Распределение по статусам (формулы COUNTIF по колонке «Статус») ---
    section(row, "Распределение по статусам")
    for status_row in stats["by_status"]:
        row += 1
        ws.cell(row=row, column=1, value=status_row["name"])
        ws.cell(
            row=row, column=2,
            value=f'=COUNTIF(ЗАДАЧИ!F:F,A{row})',
        )
    row += 2

    # --- Распределения (расчетные показатели из БД) ---
    section(row, "Распределение по категориям")
    for data_row in stats["by_category"]:
        row += 1
        ws.cell(row=row, column=1, value=data_row["name"])
        ws.cell(row=row, column=2, value=data_row["cnt"])
    row += 2

    section(row, "Распределение по исполнителям")
    for data_row in stats["by_assignee"]:
        row += 1
        ws.cell(row=row, column=1, value=data_row["name"])
        ws.cell(row=row, column=2, value=data_row["cnt"])
    row += 2

    section(row, "Распределение по приоритетам")
    for data_row in stats["by_priority"]:
        row += 1
        ws.cell(row=row, column=1, value=data_row["name"])
        ws.cell(row=row, column=2, value=data_row["cnt"])

    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 34


# ----------------------------------------------------------------------
# Лист 3 — СПРАВОЧНИКИ
# ----------------------------------------------------------------------
def _sheet_dictionaries(wb: Workbook, dictionaries: dict[str, list[dict[str, Any]]]) -> None:
    ws = wb.create_sheet("СПРАВОЧНИКИ")

    def block(start_col: int, title: str, headers: list[str], rows: list[dict[str, Any]],
              fields: list[str]) -> None:
        col_letter = get_column_letter(start_col)
        ws.cell(row=1, column=start_col, value=title).font = Font(bold=True)
        for offset, header in enumerate(headers):
            cell = ws.cell(row=2, column=start_col + offset, value=header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
        for row_index, data_row in enumerate(rows, start=3):
            for offset, field_name in enumerate(fields):
                value = data_row.get(field_name)
                if field_name in {"is_active", "is_final"}:
                    value = "да" if value else "нет"
                ws.cell(row=row_index, column=start_col + offset, value=value)

    block(1, "Категории", ["Название", "Активна"], dictionaries["categories"],
          ["name", "is_active"])
    block(4, "Статусы", ["Название", "Порядок", "Завершающий", "Активен"],
          dictionaries["statuses"], ["name", "sort_order", "is_final", "is_active"])
    block(9, "Приоритеты", ["Название", "Порядок", "Активен"],
          dictionaries["priorities"], ["name", "sort_order", "is_active"])
    block(13, "Участники команды", ["Telegram ID", "Username", "Имя", "Роль",
                                      "Активен", "В команде с"],
          dictionaries["users"],
          ["id", "username", "full_name", "role", "is_active", "joined_at"])
    for start_col, width in ((1, 22), (2, 12), (4, 10), (5, 10), (6, 10),
                              (7, 10), (9, 16), (10, 14), (11, 12), (12, 12),
                              (13, 12), (14, 24), (15, 14), (16, 22),
                              (17, 22)):
        ws.column_dimensions[get_column_letter(start_col)].width = width


# ----------------------------------------------------------------------
# Публичная функция
# ----------------------------------------------------------------------
def write_xlsx(tasks: list[dict[str, Any]], stats: dict[str, Any],
               dictionaries: dict[str, list[dict[str, Any]]],
               exports_dir: Path, timezone_name: str) -> Path:
    """Формирует XLSX-файл и возвращает путь к нему."""
    exports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H-%M")
    path = exports_dir / f"tasks_{stamp}.xlsx"

    wb = Workbook()
    _sheet_tasks(wb, tasks, timezone_name, dictionaries)
    _sheet_summary(wb, tasks, stats)
    _sheet_dictionaries(wb, dictionaries)
    wb.save(path)
    logger.info("XLSX-экспорт создан: %s (%d задач)", path.name, len(tasks))
    return path

"""Тесты экспорта: CSV (UTF-8 BOM) и Excel (3 листа, оформление, сводка)."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from app.database.repositories.settings import SettingsRepository
from app.exports.csv_export import CSV_HEADERS, build_csv, write_csv_file
from app.exports.excel_export import write_xlsx
from app.services.statistics_service import StatisticsService


async def _create_tasks(task_service, settings_repo, admin_user, count: int) -> list[int]:
    """Создаёт count тестовых задач и возвращает их ID."""
    category = (await settings_repo.list_categories(only_active=True))[0]["id"]
    priority = (await settings_repo.list_priorities(only_active=True))[0]["id"]
    ids = []
    for index in range(count):
        ids.append(await task_service.create_task(
            title=f"Тест {index:02d}",
            description="Комментарий для экспорта",
            category_id=category,
            priority_id=priority,
            assigned_to=None,
            due_date_iso=None,
            user_id=admin_user["id"],
            timezone_name="UTC",
        ))
    return ids


async def test_csv_structure(task_service, settings_repo, admin_user, tmp_path) -> None:
    """CSV: русские заголовки, BOM, разделитель ';', данные задач."""
    await _create_tasks(task_service, settings_repo, admin_user, count=2)
    tasks = await task_service.tasks.all_for_export()
    first_line = build_csv(tasks, "UTC").split("\n")[0]
    assert first_line == ";".join(CSV_HEADERS)

    path = write_csv_file(tasks, tmp_path, "UTC")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM для Excel


async def test_csv_escapes_semicolons(task_service, settings_repo, admin_user) -> None:
    """Значения с ';' и кавычками экранируются по правилам CSV."""
    category = (await settings_repo.list_categories(only_active=True))[0]["id"]
    await task_service.create_task(
        title="Задача; с точками; запятыми", description='Кавычки "внутри"',
        category_id=category, priority_id=1, assigned_to=None,
        due_date_iso=None, user_id=admin_user["id"], timezone_name="UTC")
    content = build_csv(await task_service.tasks.all_for_export(), "UTC")
    assert '"Задача; с точками; запятыми"' in content
    assert '"Кавычки ""внутри"""' in content


async def test_csv_empty_base(task_service, tmp_path) -> None:
    """Пустая база: CSV содержит только строку заголовков."""
    tasks = await task_service.tasks.all_for_export()
    assert tasks == []
    content = build_csv(tasks, "UTC")
    lines = content.strip().split("\n")
    assert lines == [";".join(CSV_HEADERS)]


async def test_xlsx_three_sheets(task_service, settings_repo, admin_user,
                                 tmp_path: Path) -> None:
    """Excel содержит ровно три листа: ЗАДАЧИ, СВОДКА, СПРАВОЧНИКИ."""
    await _create_tasks(task_service, settings_repo, admin_user, count=3)
    stats = await StatisticsService(task_service.db).collect()
    dictionaries = await settings_repo.all_for_export()
    path = write_xlsx(await task_service.tasks.all_for_export(), stats,
                      dictionaries, tmp_path, "UTC")

    wb = load_workbook(path)
    assert wb.sheetnames == ["ЗАДАЧИ", "СВОДКА", "СПРАВОЧНИКИ"]

    headers = [cell.value for cell in wb["ЗАДАЧИ"][1]]
    assert len(headers) == 12
    assert headers[0] == "ID" and headers[-1] == "Дата завершения"


async def test_xlsx_content_and_style(task_service, settings_repo, admin_user,
                                      tmp_path: Path) -> None:
    """Данные задач в Excel + автофильтр + закрепление шапки + ширины колонок."""
    await _create_tasks(task_service, settings_repo, admin_user, count=5)
    stats = await StatisticsService(task_service.db).collect()
    dictionaries = await settings_repo.all_for_export()
    path = write_xlsx(await task_service.tasks.all_for_export(), stats,
                      dictionaries, tmp_path, "UTC")

    ws = load_workbook(path)["ЗАДАЧИ"]
    assert ws.max_row == 6                       # шапка + 5 задач
    assert ws.cell(row=2, column=2).value == "Тест 00"
    assert ws.cell(row=2, column=6).value == "Новая"
    assert ws.auto_filter.ref is not None        # фильтры включены
    assert ws.freeze_panes == "A2"               # шапка закреплена
    assert (ws.column_dimensions["B"].width or 0) > 10  # ширины настроены


async def test_xlsx_summary_numbers(task_service, settings_repo, admin_user,
                                    tmp_path: Path) -> None:
    """Сводные показатели на листе СВОДКА соответствуют базе."""
    await _create_tasks(task_service, settings_repo, admin_user, count=4)
    stats = await StatisticsService(task_service.db).collect()
    dictionaries = await settings_repo.all_for_export()
    path = write_xlsx(await task_service.tasks.all_for_export(), stats,
                      dictionaries, tmp_path, "UTC")

    ws = load_workbook(path)["СВОДКА"]
    values = {}
    for row in ws.iter_rows(values_only=False):
        if row[0].value is not None:
            values[row[0].value] = row[1].value if len(row) > 1 else None

    assert stats["total"] == 4
    # «Всего задач» — живая формула COUNTA по листу ЗАДАЧИ.
    assert str(values["Всего задач"]).startswith("=COUNTA")
    assert values["Просрочено"] == stats["overdue"] == 0


async def test_xlsx_dictionary_sheet(task_service, settings_repo, admin_user,
                                     tmp_path: Path) -> None:
    """Лист СПРАВОЧНИКИ: категории, статусы, приоритеты, участники."""
    await _create_tasks(task_service, settings_repo, admin_user, count=1)
    stats = await StatisticsService(task_service.db).collect()
    dictionaries = await settings_repo.all_for_export()
    path = write_xlsx(await task_service.tasks.all_for_export(), stats,
                      dictionaries, tmp_path, "UTC")

    ws = load_workbook(path)["СПРАВОЧНИКИ"]
    all_values = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
    for expected in ("Категории", "Статусы", "Приоритеты", "Участники команды",
                     "Общие", "Новая", "Низкий", "Администратор Тестов"):
        assert expected in all_values


async def test_export_is_snapshot_not_bidirectional(task_service, settings_repo,
                                                    admin_user, tmp_path: Path) -> None:
    """Изменения в Excel не возвращаются в SQLite (экспорт = снимок)."""
    await _create_tasks(task_service, settings_repo, admin_user, count=1)
    stats = await StatisticsService(task_service.db).collect()
    dictionaries = await settings_repo.all_for_export()
    path = write_xlsx(await task_service.tasks.all_for_export(), stats,
                      dictionaries, tmp_path, "UTC")

    # «Правим» файл Excel внешне.
    wb = load_workbook(path)
    wb["ЗАДАЧИ"].cell(row=2, column=2, value="СОВСЕМ ДРУГОЕ НАЗВАНИЕ")
    wb.save(path)

    # База данных — источник истины — не изменилась.
    task = (await task_service.tasks.all_for_export())[0]
    assert task["title"] == "Тест 00"

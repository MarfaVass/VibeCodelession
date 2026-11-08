# -*- coding: utf-8 -*-
"""Smoke-тест: отчёт, диаграммы и справочник категорий без исключений.

Запуск: python smoke_test.py   (из каталога budget_book)
Части теста:
  1. отчёт (reports) и диаграммы (charts) на данных пользователя
     или на демо-данных в памяти;
  2. справочник категорий: выбор по номеру, добавление, отказ на
     дубликат без учёта регистра и пробелов, восстановление из дефолта
     при повреждённом файле (проверяется во временной папке).
Тест печатает «OK» и список построенных PNG, либо FAIL с причиной.
"""

import sys
import tempfile
from pathlib import Path

import categories
import charts
import demo
import reports
import storage


def run_report_and_charts() -> bool:
    """Часть 1: отчёт и диаграммы.

    Если файла данных нет (или он пуст), тест использует демо-данные
    в памяти — файл на диск не трогается.

    :return: True, если всё отработало без исключений.
    """
    data = None
    if storage.DATA_FILE.exists():
        stored = storage.load_budget()
        if reports.income_rows(stored) or reports.expense_rows(stored):
            data = stored
            source = f"файл данных {storage.DATA_FILE.name}"
    if data is None:
        data = demo.build_demo_budget()
        source = "демо-данные из demo.py (в памяти)"

    print(f"Источник данных: {source}")

    report_text = reports.format_report(data)
    if "ПЛАН-ФАКТ" not in report_text:
        print("Ошибка: отчёт не содержит заголовка.")
        return False
    print("--- Отчёт (начало) ---")
    print("\n".join(report_text.splitlines()[:9]))
    print("--- Отчёт (сокращён) ---")

    built = charts.build_charts(data)
    names = sorted(path.name for path in built)
    print(f"Построены диаграммы: {', '.join(names) if names else 'ни одной'}")

    if not names:
        print("Ошибка: не построена ни одна диаграмма.")
        return False
    if charts.PLAN_VS_FACT_FILE.name not in names:
        print("Ошибка: plan_vs_fact.png не построен.")
        return False
    if charts.ACTUAL_EXPENSES_FILE.name in names:
        if not charts.ACTUAL_EXPENSES_FILE.exists():
            print("Ошибка: actual_expenses.png не найден на диске.")
            return False
    return True


def run_categories(tmp_dir: Path) -> bool:
    """Часть 2: справочник категорий.

    :param tmp_dir: временная папка для тестирования файла справочника.
    :return: True, если все проверки прошли.
    """
    catalog = list(categories.DEFAULT_CATEGORIES)
    storage_file = tmp_dir / "categories.json"

    # --- Выбор по номеру ---
    ok_cases = [("1", catalog[0]), (str(len(catalog)), catalog[-1]), ("  2  ", catalog[1])]
    bad_cases = ["", "abc", "0", str(len(catalog) + 1), "-1"]
    for raw, expected in ok_cases:
        if categories.select_category_by_number(catalog, raw) != expected:
            print(f"Ошибка: выбор по номеру {raw!r} не дал {expected!r}.")
            return False
    for raw in bad_cases:
        if categories.select_category_by_number(catalog, raw) is not None:
            print(f"Ошибка: некорректный номер {raw!r} принят.")
            return False

    # --- Добавление и дубликаты (регистр и пробелы не учитываются) ---
    if not categories.add_category(catalog, "  Питомцы  ", path=storage_file):
        print("Ошибка: новая категория не добавилась.")
        return False
    if catalog[-1] != "Питомцы" or not storage_file.exists():
        print("Ошибка: категория не добавлена в список и файл.")
        return False
    for duplicate in ("ПИТОМЦЫ", "  питомцы "):
        if categories.add_category(catalog, duplicate, path=storage_file):
            print(f"Ошибка: дубликат {duplicate!r} прошёл проверку.")
            return False
    if len(catalog) != len(categories.DEFAULT_CATEGORIES) + 1:
        print("Ошибка: дубликат всё-таки попал в список.")
        return False

    # --- Повреждённый файл восстанавливается из дефолта ---
    storage_file.write_text("{ это не json", encoding="utf-8")
    restored = categories.load_categories(path=storage_file)
    if restored != list(categories.DEFAULT_CATEGORIES):
        print("Ошибка: справочник не восстановился из дефолта после порчи файла.")
        return False

    print("Справочник: выбор по номеру, добавление, дубликаты, восстановление — ОК")
    return True


def main() -> None:
    """Точка входа smoke-теста: печатает результат отдельной строкой."""
    with tempfile.TemporaryDirectory() as tmp:
        ok = run_report_and_charts() and run_categories(Path(tmp))
    print("OK" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

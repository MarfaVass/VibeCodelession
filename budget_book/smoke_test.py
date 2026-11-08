# -*- coding: utf-8 -*-
"""Smoke-тест веб-приложения: логика без Streamlit.

Запуск: python smoke_test.py   (из каталога budget_book)
Проверяется всё, кроме Streamlit-Интерфейса (он отмечается в REPORT.md
как проверяемый вручную):
  1. модель данных и миграция старого CLI-формата из storage;
  2. справочник статей: добавление, отказ на дубликат без учёта
     регистра и пробелов, восстановление из дефолта при порче файла;
  3. отчёт: план, факт, разница, процент (прочерк при нулевом плане);
  4. диаграммы: обе PNG на данных текущего месяца;
  5. валидация сумм: запятая, пробелы, ноль как «пустое поле»,
     отрицательные — отклонение.
"""

import sys
import tempfile
from pathlib import Path

import categories
import charts
import demo
import models
import reports
import storage
import validators


def run_storage_and_demo(tmp: Path) -> bool:
    """Часть 1: данные и миграция CLI-формата.

    :param tmp: временная папка, чтобы не трогать пользовательские данные.
    :return: True при успехе.
    """
    budget = demo.build_demo_budget()
    if models.month_key(0, 1) != "0000-01":  # проверка ключа месяца
        return False
    key = models.month_keys(budget)[0]
    block = models.ensure_month(budget, key)
    checks = [
        ("план доходов >= 2", len(block[models.KEY_PLANNED_INCOME]) >= 2),
        ("план статей >= 4", len(block[models.KEY_PLANNED_ARTICLES]) >= 4),
        ("факт расходов >= 4", len(block[models.KEY_ACTUAL_EXPENSES]) >= 4),
    ]
    for name, ok in checks:
        if not ok:
            print(f"Ошибка: демо-данные неполные ({name}).")
            return False

    # Замена плановой суммы статьи и «нулевое» удаление
    models.set_planned_article(block, "Транспорт", 5000.0)
    if not any(e["category"] == "Транспорт" and e["amount"] == 5000.0
               for e in block[models.KEY_PLANNED_ARTICLES]):
        print("Ошибка: set_planned_article не заменил сумму.")
        return False
    models.set_planned_article(block, "Транспорт", 0.0)
    if any(e["category"] == "Транспорт" for e in block[models.KEY_PLANNED_ARTICLES]):
        print("Ошибка: нулевая сумма не удалила статью из плана.")
        return False

    # Миграция CLI-формата: план в корне, mandatory/purchases
    legacy = {
        "planned_income": [{"source": "Зарплата", "amount": 80000}],
        "planned_expenses": {
            "mandatory": [{"category": "Жильё", "name": "Аренда", "amount": 30000},
                          {"category": "Жильё", "name": "ЖКХ", "amount": 6000}],
            "purchases": [{"category": "Одежда", "name": "Куртка", "amount": 12000}],
        },
        "actual_expenses": [{"category": "Продукты", "name": "Пятерочка",
                             "amount": 1500, "date": "2026-11-05"}],
    }
    migrated = models.migrate_legacy_budget(legacy)
    mkey = models.month_keys(migrated)[0]
    mblock = migrated[models.KEY_MONTHS][mkey]
    if mblock[models.KEY_PLANNED_INCOME][0]["amount"] != 80000:
        print("Ошибка: миграция потерял плановый доход.")
        return False
    zhilyo = next(e for e in mblock[models.KEY_PLANNED_ARTICLES]
                  if e["category"] == "Жильё")
    if zhilyo["amount"] != 36000:  # 30000 + 6000 слились по категории
        print(f"Ошибка: миграция не слила статьи по категории (получено {zhilyo}).")
        return False
    if mblock[models.KEY_ACTUAL_EXPENSES][0]["comment"] != "Пятерочка":
        print("Ошибка: миграция не превратила name в комментарий.")
        return False

    print("Данные: месяца, статьи, миграция CLI-формата — OK")
    return True


def run_categories(tmp: Path) -> bool:
    """Часть 2: справочник статей.

    :param tmp: временная папка для файла справочника.
    :return: True при успехе.
    """
    catalog = list(categories.DEFAULT_CATEGORIES)
    storage_file = tmp / "categories.json"

    if not categories.add_category(catalog, "  Питомцы  ", path=storage_file):
        print("Ошибка: новая статья не добавилась.")
        return False
    for duplicate in ("ПИТОМЦЫ", "  питомцы "):
        if categories.add_category(catalog, duplicate, path=storage_file):
            print(f"Ошибка: дубликат {duplicate!r} прошёл проверку.")
            return False
    if categories.category_color_index(catalog, "Питомцы") != len(catalog) - 1:
        print("Ошибка: индекс новой статьи в справочнике определён неверно.")
        return False

    storage_file.write_text("{ это не json", encoding="utf-8")
    restored = categories.load_categories(path=storage_file)
    if restored != list(categories.DEFAULT_CATEGORIES):
        print("Ошибка: справочник не восстановился из дефолта после порчи файла.")
        return False

    print("Справочник: добавление, дубликаты, цвет по индексу, восстановление — OK")
    return True


def run_reports_and_charts(tmp: Path) -> bool:
    """Часть 3 и 4: отчёт и диаграммы на демо-данных (в памяти и в temp).

    :param tmp: временная папка для PNG, чтобы не смешивать с проектом.
    :return: True при успехе.
    """
    year, month_num = 2026, 5
    key = models.month_key(year, month_num)
    budget = demo.build_demo_budget(key)

    rows = reports.article_rows(budget, key)
    zhilyo = next(row for row in rows if row["article"] == "Жильё")
    if zhilyo["plan"] != 36000 or zhilyo["fact"] != 35200:
        print(f"Ошибка: план/факт статьи «Жильё» посчитаны неверно: {zhilyo}.")
        return False
    if zhilyo["diff"] != 800:  # 36 000 − 35 200
        print(f"Ошибка: разница план-факт посчитана неверно: {zhilyo}.")
        return False
    if zhilyo["percent"] is None or abs(zhilyo["percent"] - 35200 / 36000) > 1e-9:
        print(f"Ошибка: процент от плана посчитан неверно: {zhilyo}.")
        return False

    # Статья без плана, но с фактом — процент-прочерк в текстовом отчёте
    block = models.ensure_month(budget, key)
    block[models.KEY_ACTUAL_EXPENSES].append(
        models.make_actual_expense("Прочее", "незапланированное", 100.0,
                                   f"{key}-15"))
    report_text = reports.format_report(budget, key)
    pricherk_line = [line for line in report_text.splitlines() if "Прочее" in line]
    if not pricherk_line or reports.PERCENT_DASH not in pricherk_line[-1]:
        print(f"Ошибка: при нулевом плане нет прочерка: {pricherk_line}.")
        return False

    # Пустой месяц — пустой отчёт и «нет данных»
    empty_key = models.month_key(year, 6)
    if reports.article_rows(budget, empty_key):
        print("Ошибка: пустой месяц отдал статьи.")
        return False
    if reports.NO_DATA not in reports.format_report(budget, empty_key):
        print("Ошибка: для пустого месяца нет пометки «нет данных».")
        return False

    catalog = categories.load_categories()
    bar = charts.build_plan_vs_fact(rows, catalog, key,
                                    path=tmp / charts.PLAN_VS_FACT_FILE.name)
    pie = charts.build_actual_expenses_pie(
        block[models.KEY_ACTUAL_EXPENSES], catalog,
        path=tmp / charts.ACTUAL_EXPENSES_FILE.name)
    if bar is None or not bar.exists():
        print("Ошибка: столбчатая диаграмма не построена.")
        return False
    if pie is None or not pie.exists():
        print("Ошибка: круговая диаграмма не построена.")
        return False

    # Пустой факт месяца — pie не строится
    if charts.build_actual_expenses_pie(
            models.ensure_month(budget, empty_key)[models.KEY_ACTUAL_EXPENSES],
            catalog, path=tmp / "empty_pie.png") is not None:
        print("Ошибка: круговая построилась без фактических расходов.")
        return False

    print("Отчёт (план/факт/разница/процент) и обе диаграммы — OK")
    return True


def run_validators() -> bool:
    """Часть 5: суммы и строки.

    :return: True при успехе.
    """
    cases = {
        "99,50": 99.50, "1 000": 1000.0, "1200.5": 1200.5, "0,99": 0.99,
    }
    for raw, expected in cases.items():
        got = validators.parse_amount(raw)
        if got != expected:
            print(f"Ошибка: сумма {raw!r} -> {got!r}, ожидалось {expected!r}.")
            return False
    rejects = ["-5", "0", "", "  ", "abc", "NaN", "inf", None, "1e400", "0,0"]
    for raw in rejects:
        if validators.parse_amount(raw) is not None:
            print(f"Ошибка: некорректная сумма {raw!r} принята.")
            return False
    if validators.clean_text("  привет  ") != "привет" or validators.clean_text("") != "":
        print("Ошибка: чистка текста работает неверно.")
        return False
    print("Валидация сумм и строк — OK")
    return True


def main() -> None:
    """Точка входа smoke-теста: печатает результат отдельной строкой."""
    with tempfile.TemporaryDirectory() as tmp:
        ok = (run_storage_and_demo(Path(tmp))
              and run_categories(Path(tmp))
              and run_reports_and_charts(Path(tmp))
              and run_validators())
    print("OK" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

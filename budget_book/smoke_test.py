# -*- coding: utf-8 -*-
"""Smoke-тест веб-приложения: логика без Streamlit.

Запуск: python smoke_test.py   (из каталога budget_book)
Streamlit-интерфейс автотестами не покрыт (проверяется вручную —
см. REPORT.md). Тестируется всё остальное:
  1. модель: месяц-блоки, план по (группа, подкатегория), входящий
     остаток, миграция CLI-формата и плоских записей v2 (→ «Прочее»);
  2. двухуровневый справочник: группа/подкатегория добавляются,
     дубликаты отклоняются (регистр и пробелы игнорируются), плоский
     файл мигрируется, повреждённый восстанавливается из дефолта;
  3. удаление статьи: записи переносятся в «Прочее» (группа и
     подкатегория), «Прочее» защищено от удаления;
  4. отчёт по группам с раскрытием подкатегорий: план, факт, разница,
     процент (прочерк при нулевом плане), пустой месяц;
  5. диаграммы по группам: обе PNG; круговая не строится без трат;
  6. валидация сумм: запятая, пробелы, ноль как «пустое поле»,
     отрицательные и мусор отклоняются.
"""

import json
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
    """Часть 1: месяцы, статьи, миграции (в памяти, без файлов данных).

    :param tmp: временная папка.
    :return: True при успехе.
    """
    budget = demo.build_demo_budget("2026-11")
    if models.month_key(0, 1) != "0000-01":
        return False
    block = models.ensure_month(budget, "2026-11")
    checks = [
        ("входящий остаток", models.get_carryover(block) == 15400),
        ("план доходов >= 2", len(block[models.KEY_PLANNED_INCOME]) >= 2),
        ("план статей >= 5", len(block[models.KEY_PLANNED_ARTICLES]) >= 5),
        ("факт расходов >= 5", len(block[models.KEY_ACTUAL_EXPENSES]) >= 5),
        ("все записи двухуровневые", all(models.KEY_GROUP in entry
                                         for entry in block[models.KEY_ACTUAL_EXPENSES])),
    ]
    for name, ok in checks:
        if not ok:
            print(f"Ошибка: демо-данные неполные ({name}).")
            return False

    # Замена плановой суммы подкатегории и удаление нулём
    models.set_planned_article(block, "Жильё", "Аренда", 99000.0)
    matching = [e for e in block[models.KEY_PLANNED_ARTICLES]
                if e["group"] == "Жильё" and e["category"] == "Аренда"]
    if len(matching) != 1 or matching[0]["amount"] != 99000.0:
        print("Ошибка: set_planned_article не заменил сумму подкатегории.")
        return False
    models.set_planned_article(block, "Жильё", "Аренда", 0.0)
    if any(e["group"] == "Жильё" and e["category"] == "Аренда"
           for e in block[models.KEY_PLANNED_ARTICLES]):
        print("Ошибка: нулевая сумма не удалила подкатегорию из плана.")
        return False

    # Входящий остаток: запись и чтение (в том числе отрицательный)
    models.set_carryover(block, -2500.0)
    if models.get_carryover(block) != -2500.0:
        print("Ошибка: входящий остаток не сохранился.")
        return False

    # --- Миграция v2 (плоские подкатегории в месяцах) → «Прочее» ---
    v2_block = {
        models.KEY_PLANNED_INCOME: [{"source": "Зарплата", "amount": 80000}],
        models.KEY_PLANNED_ARTICLES: [{"category": "Аренда", "amount": 30000}],
        models.KEY_ACTUAL_EXPENSES: [
            {"category": "Аренда", "name": "Квартира", "amount": 30000,
             "date": "2026-11-05"},
        ],
    }
    moved = models.migrate_flat_entries(v2_block)
    fact = v2_block[models.KEY_ACTUAL_EXPENSES][0]
    if fact.get(models.KEY_GROUP) != "Прочее" or fact["category"] != "Аренда":
        print(f"Ошибка: плоские записи не ушли в «Прочее»: {fact}.")
        return False
    if moved != ["Аренда"]:
        print(f"Ошибка: список перенесённых имён неверный: {moved}.")
        return False
    if v2_block[models.KEY_PLANNED_ARTICLES][0]["group"] != "Прочее":
        print("Ошибка: плоский план не попал в «Прочее».")
        return False

    # --- Миграция CLI-формата (план/факт в корне) ---
    legacy = {
        "planned_income": [{"source": "Зарплата", "amount": 80000}],
        "planned_expenses": {
            "mandatory": [{"category": "Аренда", "name": "Квартира", "amount": 30000}],
            "purchases": [{"category": "Аренда", "name": "Депозит", "amount": 6000}],
        },
        "actual_expenses": [{"category": "Еда", "name": "Пятерочка",
                             "amount": 1500, "date": "2026-11-05"}],
    }
    migrated = models.migrate_legacy_budget(legacy)
    mkey = models.month_keys(migrated)[0]
    mblock = migrated[models.KEY_MONTHS][mkey]
    arenda = next(e for e in mblock[models.KEY_PLANNED_ARTICLES]
                  if e["category"] == "Аренда")
    if arenda["group"] != "Прочее" or arenda["amount"] != 36000:  # 30000+6000
        print(f"Ошибка: CLI-миграция не слила статьи: {arenda}.")
        return False
    if mblock[models.KEY_ACTUAL_EXPENSES][0]["category"] != "Еда":
        print("Ошибка: CLI-миграция потеряла факт.")
        return False

    print("Данные: месяцы, план по подкатегориям, входящий остаток, миграции — OK")
    return True


def run_categories(tmp: Path) -> bool:
    """Часть 2: двухуровневый справочник (файлы — во временной папке).

    :param tmp: временная папка.
    :return: True при успехе.
    """
    catalog = {g: list(s) for g, s in categories.DEFAULT_CATEGORIES.items()}
    storage_file = tmp / "categories.json"

    # Добавление группы с подкатегориями и без
    if categories.add_group(catalog, "Хобби", ["Фото"], path=storage_file) != categories.ADDED:
        print("Ошибка: новая группа не добавилась.")
        return False
    if catalog["Хобби"] != ["Фото"] or not storage_file.exists():
        print("Ошибка: группа с подкатегориями не сохранилась в файл.")
        return False
    if categories.add_group(catalog, "Туризм", None, path=storage_file) != categories.ADDED:
        print("Ошибка: пустая группа не добавилась.")
        return False
    # Дубликаты группы: без учёта регистра и с обрезкой
    for duplicate in ("хобби", "  ТУРИЗМ "):
        if categories.add_group(catalog, duplicate, None, path=storage_file) != categories.DUPLICATE:
            print(f"Ошибка: дубликат группы {duplicate!r} прошёл проверку.")
            return False
    # Дубликаты подкатегорий, несуществующая группа
    if categories.add_subcategory(catalog, "Хобби", "фото", path=storage_file) != categories.DUPLICATE:
        print("Ошибка: дубликат подкатегории прошёл проверку.")
        return False
    if categories.add_subcategory(catalog, "Нет такой группы", "Разное", path=storage_file) != categories.NO_GROUP:
        print("Ошибка: подкатегория добавилась в несуществующую группу.")
        return False
    if categories.add_subcategory(catalog, "Хобби", "  Велосипед  ", path=storage_file) != categories.ADDED:
        print("Ошибка: новая подкатегория не добавилась.")
        return False

    # Плоский старый файл мигрируется: знакомые группы получают дефолтные подкатегории
    flat_file = tmp / "flat.json"
    flat_file.write_text(json.dumps(["Жильё", "Продукты", "Кафе"], ensure_ascii=False),
                         encoding="utf-8")
    migrated_catalog = categories.load_categories(path=flat_file)
    if "Жильё" not in migrated_catalog or "Аренда" not in migrated_catalog["Жильё"]:
        print("Ошибка: плоский файл не мигрировал знакомые группы.")
        return False
    if "Продукты" in migrated_catalog or "Кафе" in migrated_catalog:
        print("Ошибка: незнакомые имена плоского файла не отброшены.")
        return False

    # Повреждённый файл восстанавливается из дефолта
    corrupted = tmp / "broken.json"
    corrupted.write_text("{ это не json", encoding="utf-8")
    restored = categories.load_categories(path=corrupted)
    if restored != {g: list(s) for g, s in categories.DEFAULT_CATEGORIES.items()}:
        print("Ошибка: справочник не восстановился из дефолта после порчи файла.")
        return False

    print("Справочник: группы, подкатегории, дубликаты, плоская миграция, дефолт — OK")
    return True


def run_deletion_flow(tmp: Path) -> bool:
    """Часть 3: удаление статей с переносом записей (models + categories).

    :param tmp: временная папка.
    :return: True при успехе.
    """
    catalog = {g: list(s) for g, s in categories.DEFAULT_CATEGORIES.items()}
    cats_file = tmp / "test-catalog.json"  # чтобы не трогать данные пользователя
    budget = demo.build_demo_budget("2026-12")  # там факты по Жильё

    # Жильё: план — Аренда, Коммуналка (2 записи); факт — Аренда,
    # Коммуналка, Ремонт (3 записи). Аренда: план+факт = 2.
    used_plan = models.count_article_usage(budget, "Жильё", "Аренда")
    used_total = models.count_article_usage(budget, "Жильё")
    if used_plan != 2 or used_total != 5:
        print(f"Ошибка: подсчёт использований неверный: {used_plan}/{used_total}.")
        return False

    # Удаление подкатегории с данными → перенос в «Прочее»
    moved = models.relocate_article_entries(budget, "Жильё", "Аренда")
    if moved != ["Жильё·Аренда"]:
        print(f"Ошибка: подпись переноса неверная: {moved}.")
        return False
    categories.add_subcategory(catalog, "Прочее", moved[0], path=None)
    if categories.remove_subcategory(catalog, "Жильё", "Аренда",
                                     path=cats_file) != categories.REMOVED:
        print("Ошибка: подкатегория не удалилась.")
        return False
    rest = [e for block in budget["months"].values()
            for e in block[models.KEY_ACTUAL_EXPENSES] if e["group"] == "Прочее"]
    if not rest or rest[0]["category"] != "Жильё·Аренда":
        print(f"Ошибка: записи подкатегории не перенеслись в «Прочее»: {rest}.")
        return False

    # Удаление группы целиком → подпись «Жильё»
    moved = models.relocate_article_entries(budget, "Жильё")
    if moved != ["Жильё"]:
        print(f"Ошибка: подпись переноса группы неверная: {moved}.")
        return False
    if categories.remove_group(catalog, "Жильё",
                               path=cats_file) != categories.REMOVED:
        print("Ошибка: группа не удалилась.")
        return False

    print("Удаление статей: подсчёт записей, перенос в «Прочее» — OK")
    return True


def run_reports_and_charts(tmp: Path) -> bool:
    """Часть 4 и 5: отчёт по группам и обе диаграммы.

    :param tmp: временная папка для PNG.
    :return: True при успехе.
    """
    key = "2026-12"
    budget = demo.build_demo_budget(key)
    catalog = categories.load_categories()

    rows = reports.group_rows(budget, key)
    zhilyo = next(row for row in rows if row["group"] == "Жильё")
    if zhilyo["plan"] != 36000 or zhilyo["fact"] != 39000:  # 30000+5200+3800
        print(f"Ошибка: план/факт группы «Жильё» неверны: {zhilyo}.")
        return False
    if zhilyo["diff"] != -3000 or abs(zhilyo["percent"] - 39000 / 36000) > 1e-9:
        print(f"Ошибка: разница/процент группы неверны: {zhilyo}.")
        return False

    subs = reports.sub_rows(budget, key, "Жильё")
    arenda = next(sub for sub in subs if sub["sub"] == "Аренда")
    if arenda["plan"] != 30000 or arenda["fact"] != 30000 or arenda["diff"] != 0:
        print(f"Ошибка: подкатегория «Аренда» посчитана неверно: {arenda}.")
        return False
    # запись в группу без подкатегории → строка «(без подкатегорий)»
    block = models.ensure_month(budget, key)
    block[models.KEY_ACTUAL_EXPENSES].append(
        models.make_actual_expense("Обучение", "", "Курсы по питону", 12000, f"{key}-15"))
    report_text = reports.format_report(budget, key)
    if reports.NO_SUBCATEGORY_LABEL not in report_text:
        print("Ошибка: план-факт группы без подкатегорий не отобразился.")
        return False

    # Проценты в отчёте и итоги
    if "Развлечения" not in report_text:
        print("Ошибка: группы нет в текстовом отчёте.")
        return False
    totals = reports.expenses_totals(budget, key)
    # доходы 80 000 + 20 000 + 5 000 = 105 000; план статей = 68 500
    if totals["balance_plan"] != 105000 - 68500:
        print(f"Ошибка: остаток посчитан неверно: {totals}.")
        return False

    empty_key = "2027-01"
    if reports.group_rows(budget, empty_key):
        print("Ошибка: пустой месяц отдал группы.")
        return False
    if reports.NO_DATA not in reports.format_report(budget, empty_key):
        print("Ошибка: для пустого месяца нет пометки «нет данных».")
        return False

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
    if charts.build_actual_expenses_pie(
            models.ensure_month(budget, empty_key)[models.KEY_ACTUAL_EXPENSES],
            catalog, path=tmp / "empty_pie.png") is not None:
        print("Ошибка: круговая построилась без фактических расходов.")
        return False

    print("Отчёт по группам (план/факт/разница/процент) и обе диаграммы — OK")
    return True


def run_validators() -> bool:
    """Часть 6: суммы и строки.

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
              and run_deletion_flow(Path(tmp))
              and run_reports_and_charts(Path(tmp))
              and run_validators())
    print("OK" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

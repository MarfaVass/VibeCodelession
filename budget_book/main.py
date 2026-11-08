# -*- coding: utf-8 -*-
"""Точка входа «Книги доходов и расходов»: меню и добавление записей.

Запуск:  python main.py   (из каталога budget_book)
"""

import sys
from datetime import date, timedelta

import categories
import models
import reports
import storage
import validators

MENU_OPTIONS = [
    ("1", "Добавить план (доход или расход)"),
    ("2", "Добавить факт (доход или расход)"),
    ("3", "Показать отчёт «План-факт»"),
    ("4", "Построить диаграммы (PNG)"),
    ("5", "Управление категориями"),
    ("0", "Выход"),
]
CATEGORIES_MENU_OPTIONS = [
    ("1", "Показать список категорий"),
    ("2", "Добавить новую категорию"),
    ("0", "Назад в главное меню"),
]
EXPENSE_KIND_OPTIONS = [
    (models.KEY_MANDATORY, "Обязательный платёж (mandatory)"),
    (models.KEY_PURCHASES, "Плановая покупка (purchases)"),
]
FACT_TYPE_OPTIONS = [("income", "Доход"), ("expense", "Расход")]
EXIT_CHOICE = "0"
EXIT_MESSAGE = "Выход из приложения. Данные сохранены, до встречи!"


def _today_string(days_back: int = 0) -> str:
    """Дата записи в формате YYYY-MM-DD; days_back — сколько дней назад.

    :param days_back: смещение в днях от сегодняшней даты.
    """
    return (date.today() - timedelta(days=days_back)).isoformat()


def _add_planned_income(budget: dict) -> None:
    """Добавить плановый доход и сразу сохранить бюджет."""
    source = validators.ask_non_empty("Источник дохода: ")
    amount = validators.ask_amount("Сумма")
    budget[models.KEY_PLANNED_INCOME].append(models.make_planned_income(source, amount))
    storage.save_budget(budget)
    print("Плановый доход добавлен.")


def _add_planned_expense(budget: dict) -> None:
    """Добавить плановый расход (mandatory или purchases) и сразу сохранить."""
    kind = validators.ask_choice("типа расхода", EXPENSE_KIND_OPTIONS)
    catalog = categories.load_categories()
    category = categories.choose_category(catalog)
    name = validators.ask_non_empty("Название позиции (например, Квартира в центре): ")
    amount = validators.ask_amount("Сумма")
    budget[models.KEY_PLANNED_EXPENSES][kind].append(
        models.make_planned_expense(kind, category, name, amount)
    )
    storage.save_budget(budget)
    print("Плановый расход добавлен.")


def _add_actual_income(budget: dict) -> None:
    """Добавить фактический доход (дата ставится автоматически) и сохранить."""
    category = validators.ask_non_empty("Категория дохода (источник): ")
    name = validators.ask_non_empty("Название поступления: ")
    amount = validators.ask_amount("Сумма")
    budget[models.KEY_ACTUAL_INCOME].append(
        models.make_actual_income(category, name, amount, _today_string())
    )
    storage.save_budget(budget)
    print(f"Фактический доход добавлен (дата {_today_string()}).")


def _add_actual_expense(budget: dict) -> None:
    """Добавить фактический расход (дата ставится автоматически) и сохранить."""
    catalog = categories.load_categories()
    category = categories.choose_category(catalog)
    name = validators.ask_non_empty("Название траты: ")
    amount = validators.ask_amount("Сумма")
    budget[models.KEY_ACTUAL_EXPENSES].append(
        models.make_actual_expense(category, name, amount, _today_string())
    )
    storage.save_budget(budget)
    print(f"Фактический расход добавлен (дата {_today_string()}).")


def _run_menu_add_plan(budget: dict) -> None:
    """Подменю «Добавить план»."""
    kind = validators.ask_choice("вида плана", [
        ("income", "Плановый доход"),
        ("expense", "Плановый расход"),
    ])
    if kind == "income":
        _add_planned_income(budget)
    else:
        _add_planned_expense(budget)


def _run_menu_add_fact(budget: dict) -> None:
    """Подменю «Добавить факт»."""
    fact_type = validators.ask_choice("вида факта", FACT_TYPE_OPTIONS)
    if fact_type == "income":
        _add_actual_income(budget)
    else:
        _add_actual_expense(budget)


def _run_menu_report(budget: dict) -> None:
    """Пункт меню «Показать отчёт»."""
    print()
    reports.print_report(budget)
    print()


def _run_menu_charts(budget: dict) -> None:
    """Пункт меню «Построить диаграммы»."""
    try:
        import charts  # импорт здесь: приложение работает и без matplotlib в памяти
        saved = charts.build_charts(budget)
    except Exception as error:  # noqa: BLE001 — меню не должно падать на графике
        print(f"Не удалось построить диаграммы: {error}", file=sys.stderr)
        return
    if charts.ACTUAL_EXPENSES_FILE not in saved:
        print("Фактических расходов пока нет — круговая диаграмма не построена.")
    for path in saved:
        print(f"Готово: {path.name}")


def _run_menu_show_categories(_budget: dict) -> None:
    """Управление категориями: показать справочник."""
    print()
    categories.print_catalog()
    print()


def _run_menu_add_category(_budget: dict) -> None:
    """Управление категориями: добавить категорию (дубликаты отклоняются)."""
    catalog = categories.load_categories()
    name = validators.ask_non_empty("Название новой категории: ")
    if categories.add_category(catalog, name):
        print(f"Категория «{name.strip()}» добавлена в справочник.")
    else:
        print("Такая категория уже есть.")


def _run_menu_categories(budget: dict) -> None:
    """Пункт меню «Управление категориями»: список и добавление."""
    while True:
        action = validators.ask_choice("действия", CATEGORIES_MENU_OPTIONS)
        if action == "0":
            return
        print()
        CATEGORIES_ACTIONS[action](budget)
        print()


CATEGORIES_ACTIONS = {
    "1": _run_menu_show_categories,
    "2": _run_menu_add_category,
}

MENU_ACTIONS = {
    "1": _run_menu_add_plan,
    "2": _run_menu_add_fact,
    "3": _run_menu_report,
    "4": _run_menu_charts,
    "5": _run_menu_categories,
}


def run_menu_loop() -> None:
    """Главный цикл приложения: показывать меню, обрабатывать выбор."""
    budget = storage.load_budget()
    print()
    print("=" * 62)
    print("Книга доходов и расходов. Данные: data/budget.json")
    print("=" * 62)
    while True:
        choice = validators.ask_choice("пункта меню", MENU_OPTIONS)
        if choice == EXIT_CHOICE:
            print(EXIT_MESSAGE)
            return
        print()
        MENU_ACTIONS[choice](budget)
        print()


def _make_output_punctuation_safe() -> None:
    """Не ронять приложение на символах, которых нет в кодировке консоли."""
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except (AttributeError, ValueError):  # не-консольные потоки
        pass


def main() -> None:
    """Точка входа: корректно завершаемся по Ctrl+C и по Ctrl+D/Ctrl+Z (EOF)."""
    _make_output_punctuation_safe()
    try:
        run_menu_loop()
    except KeyboardInterrupt:
        print()
        print("Прервано пользователем (Ctrl+C). Данные уже сохранены, до встречи!")
        sys.exit(0)
    except EOFError:
        print()
        print("Ввод завершён (Ctrl+D). Данные уже сохранены, до встречи!")
        sys.exit(0)


if __name__ == "__main__":
    main()

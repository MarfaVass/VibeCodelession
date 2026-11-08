# -*- coding: utf-8 -*-
"""Демо-данные: перезаписывает data/budget.json готовым примером месяца.

Запуск: python demo.py   (из каталога budget_book)
После этого python main.py сразу покажет живой отчёт и диаграммы.
Категории демо-записей берутся из справочника data/categories.json;
при первом запуске справочник создаётся из дефолтного списка.
"""

from datetime import date, timedelta

import categories
import models
import storage


def _demo_dates() -> dict:
    """Даты демо-записей относительно сегодняшнего дня.

    :return: словарь «имя события — дата (YYYY-MM-DD)».
    """
    today = date.today()
    days = lambda n: (today - timedelta(days=n)).isoformat()  # noqa: E731 — компактный хелпер
    return {
        "salary": days(10),
        "freelance": days(6),
        "housing_rent": days(9),
        "housing_utilities": days(7),
        "groceries_1": days(8),
        "groceries_2": days(5),
        "groceries_3": days(2),
        "transport": days(3),
        "fun": days(1),
        "health": days(4),
    }


def build_demo_budget() -> dict:
    """Собрать демо-бюджет месяца (зарплата 80 000, аренда 30 000 и т.д.).

    Расходные категории — только из справочника, причём задействовано
    несколько (Жильё, Продукты, Транспорт, Здоровье, Развлечения),
    чтобы отчёт был многострочным, а круговая — разноцветной.

    :return: структура бюджета, готовая к сохранению.
    """
    dates = _demo_dates()
    budget = models.new_budget()

    # --- План ---
    for source, amount in (("Зарплата", 80000), ("Подработка", 20000)):
        budget[models.KEY_PLANNED_INCOME].append(models.make_planned_income(source, amount))

    mandatory_plan = [
        ("Жильё", "Аренда квартиры", 30000),
        ("Жильё", "Коммунальные платежи", 6000),
        ("Продукты", "Весь месяц", 20000),
        ("Транспорт", "Проездной", 3000),
        ("Здоровье", "Лекарства на месяц", 4000),
    ]
    for category, name, amount in mandatory_plan:
        budget[models.KEY_PLANNED_EXPENSES][models.KEY_MANDATORY].append(
            models.make_planned_expense(models.KEY_MANDATORY, category, name, amount)
        )

    purchases_plan = [
        ("Развлечения", "Билеты в театр", 5000),
        ("Одежда", "Куртка к зиме", 12000),
    ]
    for category, name, amount in purchases_plan:
        budget[models.KEY_PLANNED_EXPENSES][models.KEY_PURCHASES].append(
            models.make_planned_expense(models.KEY_PURCHASES, category, name, amount)
        )

    # --- Факт ---
    budget[models.KEY_ACTUAL_INCOME].append(
        models.make_actual_income("Зарплата", "Аванс за половину месяца", 40000, dates["salary"])
    )
    budget[models.KEY_ACTUAL_INCOME].append(
        models.make_actual_income("Подработка", "Мелкий заказ", 12000, dates["freelance"])
    )

    actual_expenses = [
        ("Жильё", "Аренда квартиры", 30000, dates["housing_rent"]),
        ("Жильё", "Электричество и вода", 5200, dates["housing_utilities"]),
        ("Продукты", "Супермаркет (большая закупка)", 8500, dates["groceries_1"]),
        ("Продукты", "Супермаркет (обычные покупки)", 4200, dates["groceries_2"]),
        ("Продукты", "Рынок", 2600, dates["groceries_3"]),
        ("Транспорт", "Проездной", 3000, dates["transport"]),
        ("Развлечения", "Кино с друзьями", 1400, dates["fun"]),
        ("Здоровье", "Аптека", 1800, dates["health"]),
    ]
    for category, name, amount, spent_on in actual_expenses:
        budget[models.KEY_ACTUAL_EXPENSES].append(
            models.make_actual_expense(category, name, amount, spent_on)
        )
    return budget


def main() -> None:
    """Записать демо-бюджет в data/budget.json (справочник создаётся рядом)."""
    catalog = categories.load_categories()
    budget = build_demo_budget()
    storage.save_budget(budget)
    print(f"Демо-данные записаны в {storage.DATA_FILE}")
    print(f"Справочник категорий: {categories.CATEGORIES_FILE} ({len(catalog)} категорий)")
    print("Теперь запустите python main.py и выберите [3] — отчёт.")


if __name__ == "__main__":
    main()

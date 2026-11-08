# -*- coding: utf-8 -*-
"""Демо-данные: перезаписывает data/budget.json готовым примером месяца.

Запуск: python demo.py   (из каталога budget_book)
Создаёт блок текущего календарного месяца (плюс предыдущий — чтобы
видно было, что месяцы держатся отдельно). Категории демо-записей
берутся из справочника data/categories.json; при первом запуске
справочник создаётся из дефолтного списка.
"""

from datetime import date

import categories
import models
import storage


def build_demo_budget(at_month: str = None) -> dict:
    """Собрать демо-бюджет месяца (зарплата 80 000, аренда 30 000 и т.д.).

    Задействовано несколько статей (Жильё, Продукты, Транспорт,
    Здоровье, Развлечения, Одежда), чтобы таблица была многострочной,
    а круговая диаграмма — разноцветной.

    :param at_month: ключ месяца «YYYY-MM»; None — текущий календарный.
    :return: структура бюджета, готовая к сохранению.
    """
    year, month = models.parse_month_key(at_month) if at_month else date.today().timetuple()[:2]
    key = models.month_key(year, month)
    budget = models.new_budget()
    _fill_month(budget, key, year, month)
    return budget


def _fill_month(budget: dict, key: str, year: int, month: int) -> None:
    """Заполнить блок месяца демо-записями.

    :param budget: структура бюджета (изменяется на месте).
    :param key: ключ месяца.
    :param year: год для дат записей.
    :param month: месяц для дат записей.
    """
    block = models.ensure_month(budget, key)

    def day(day_number: int) -> str:
        """Дата внутри месяца по номеру дня.

        :param day_number: день месяца 1..31.
        """
        return models.month_key(year, month) + f"-{day_number:02d}"

    # --- План доходов ---
    for source, amount in (("Зарплата", 80000), ("Подработка", 20000)):
        block[models.KEY_PLANNED_INCOME].append(models.make_planned_income(source, amount))

    # --- План статей ---
    for category, amount in (
        ("Жильё", 36000),      # аренда 30 000 + коммунальные 6 000
        ("Продукты", 20000),
        ("Транспорт", 3000),
        ("Здоровье", 4000),
        ("Развлечения", 5000),
        ("Одежда", 12000),
    ):
        models.set_planned_article(block, category, amount)

    # --- Факт ---
    actual_expenses = [
        ("Жильё", "Аренда квартиры", 30000, day(5)),
        ("Жильё", "Электричество и вода", 5200, day(7)),
        ("Продукты", "Супермаркет (большая закупка)", 8500, day(4)),
        ("Продукты", "Супермаркет (обычные покупки)", 4200, day(9)),
        ("Продукты", "Рынок", 2600, day(13)),
        ("Транспорт", "Проездной", 3000, day(6)),
        ("Развлечения", "Кино с друзьями", 1400, day(12)),
        ("Здоровье", "Аптека", 1800, day(8)),
    ]
    for category, comment, amount, spent_on in actual_expenses:
        block[models.KEY_ACTUAL_EXPENSES].append(
            models.make_actual_expense(category, comment, amount, spent_on)
        )


def main() -> None:
    """Записать демо-бюджет в data/budget.json (справочник создаётся рядом)."""
    catalog = categories.load_categories()
    budget = build_demo_budget()
    storage.save_budget(budget)
    print(f"Демо-данные записаны в {storage.DATA_FILE}")
    print(f"Справочник статей: {categories.CATEGORIES_FILE} ({len(catalog)} категорий)")
    print("Теперь запустите: streamlit run app.py")


if __name__ == "__main__":
    main()

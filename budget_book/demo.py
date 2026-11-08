# -*- coding: utf-8 -*-
"""Демо-данные: перезаписывает data/budget.json готовым примером месяца.

Запуск: python demo.py   (из каталога budget_book)
Создаёт блок текущего календарного месяца. Статьи демо в двух уровнях
(группа → подкатегория) и только из справочника data/categories.json —
при первом запуске справочник создаётся из дефолтного списка.
"""

from datetime import date

import categories
import models
import storage


def build_demo_budget(at_month: str = None) -> dict:
    """Собрать демо-бюджет месяца (зарплата 80 000, аренда 30 000 и т.д.).

    Задействовано несколько групп (Жильё, Транспорт, Здоровье,
    Развлечения, Одежда) с подкатегориями — таблица отчёта получается
    многострочной, круговая диаграмма — разноцветной.

    :param at_month: ключ месяца «YYYY-MM»; None — текущий календарный.
    :return: структура бюджета, готовая к сохранению.
    """
    if at_month:
        year, month = models.parse_month_key(at_month)
        year, month = (year, month) if year and month else date.today().timetuple()[:2]
    else:
        year, month = date.today().timetuple()[:2]
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
    models.set_carryover(block, 15400)  # входящий остаток примера

    # --- План доходов: быстрый разрез «зарплата/подработка/прочий» ---
    for source, amount in (("Зарплата", 80000), ("Подработка", 20000),
                           ("Прочий доход", 5000)):
        models.set_planned_income(block, source, amount)

    # --- План по подкатегориям двухуровневого справочника ---
    demos_plan = [
        ("Жильё", "Аренда", 30000),
        ("Жильё", "Коммунальные услуги", 6000),
        ("Транспорт", "Топливо", 8000),
        ("Транспорт", "Общественный", 1500),
        ("Здоровье", "Аптека", 4000),
        ("Развлечения", "Кино", 3000),
        ("Развлечения", "Кафе", 4000),
        ("Одежда", "Верхняя одежда", 12000),
    ]
    for group, sub, amount in demos_plan:
        models.set_planned_article(block, group, sub, amount)

    # --- Факт ---
    def day(day_number: int) -> str:
        """Дата внутри месяца по номеру дня.

        :param day_number: день месяца 1..31.
        """
        return models.month_key(year, month) + f"-{day_number:02d}"

    actual_expenses = [
        ("Жильё", "Аренда", "Аренда квартиры", 30000, day(5)),
        ("Жильё", "Коммунальные услуги", "Электричество и вода", 5200, day(7)),
        ("Жильё", "Ремонт", "Замена смесителя", 3800, day(14)),
        ("Транспорт", "Топливо", "Заправка", 6400, day(9)),
        ("Транспорт", "Общественный", "Проездной", 3000, day(6)),
        ("Одежда", "Обувь", "Кроссовки к осени", 4800, day(15)),
        ("Здоровье", "Аптека", "Аптека", 1800, day(8)),
        ("Развлечения", "Кафе", "Ужин с друзьями", 2600, day(13)),
        ("Развлечения", "Кино", "Два билета", 1400, day(12)),
    ]
    for group, sub, comment, amount, spent_on in actual_expenses:
        block[models.KEY_ACTUAL_EXPENSES].append(
            models.make_actual_expense(group, sub, comment, amount, spent_on))


def main() -> None:
    """Записать демо-бюджет в data/budget.json (справочник создаётся рядом)."""
    catalog = categories.load_categories()
    budget = build_demo_budget()
    storage.save_budget(budget)
    print(f"Демо-данные записаны в {storage.DATA_FILE}")
    print(f"Справочник групп: {categories.CATEGORIES_FILE} "
          f"({len(catalog)} групп, "
          f"{sum(len(s) for s in catalog.values())} подкатегорий)")
    print("Теперь запустите: streamlit run app.py")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Модель данных «Книги доходов и расходов».

Бюджет хранится по месяцам: каждый месяц — отдельный блок, поэтому
выбор месяца сверху страницы сразу переключает и план, и отчёт.
Статьи расходов — двухуровневые: группа + подкатегория (см.
data/categories.json). Записи — обычные словари, сериализуемые в JSON.
Здесь же — миграции данных CLI-версии и версии с плоскими категориями.

Формат блока месяца:
  planned_income:   [{source, amount}]
  planned_articles: [{group, category, amount}]   category = подкатегория
  actual_expenses:  [{group, category, comment, amount, date}]
"""

from typing import Dict, List, Optional, Tuple

# --- Ключи структуры бюджета ---------------------------------------------------
KEY_MONTHS = "months"                 # {«YYYY-MM»: блок месяца}

# --- Ключи блока месяца --------------------------------------------------------
KEY_PLANNED_INCOME = "planned_income"   # [{source, amount}]
KEY_PLANNED_ARTICLES = "planned_articles"  # [{group, category, amount}]
KEY_ACTUAL_EXPENSES = "actual_expenses"  # [{group, category, comment, amount, date}]
KEY_CARRYOVER = "carryover"             # входящий остаток месяца (число)

# Быстрые источники планового дохода на вкладке «План»
QUICK_INCOME_SOURCES = ("Зарплата", "Подработка", "Прочий доход")

# --- Ключи записей -------------------------------------------------------------
KEY_CATEGORY = "category"   # подкатегория
KEY_GROUP = "group"         # группа (уровень 1)
KEY_SOURCE = "source"
KEY_AMOUNT = "amount"
KEY_NAME = "name"
KEY_COMMENT = "comment"
KEY_DATE = "date"


def month_key(year: int, month: int) -> str:
    """Собрать ключ месяца «YYYY-MM».

    :param year: год (полный, например 2026).
    :param month: месяц 1..12.
    :return: строка-ключ.
    """
    return f"{year:04d}-{month:02d}"


def parse_month_key(key: str) -> Tuple[int, int]:
    """Разобрать ключ месяца обратно в (год, месяц).

    :param key: строка «YYYY-MM».
    :return: пара (год, месяц) или (0, 0), если ключ не распознан.
    """
    try:
        year, month = key.split("-")[:2]
        return int(year), int(month)
    except (ValueError, AttributeError, TypeError):
        return (0, 0)


def month_of_date(iso_date: str) -> Optional[str]:
    """Ключ месяца из полной даты «YYYY-MM-DD».

    :param iso_date: дата-строка.
    :return: «YYYY-MM» или None, если дата не распознана.
    """
    if not iso_date:
        return None
    return "-".join(str(iso_date).split("-")[:2])


def new_budget() -> dict:
    """Создать пустую структуру бюджета."""
    return {KEY_MONTHS: {}}


def empty_month_block() -> Dict[str, list]:
    """Создать пустой блок месяца (план доходов, план статей, факты)."""
    return {
        KEY_PLANNED_INCOME: [],
        KEY_PLANNED_ARTICLES: [],
        KEY_ACTUAL_EXPENSES: [],
    }


def get_carryover(block: dict) -> float:
    """Входящий остаток месяца (сколько денег принесено из прошлых месяцев).

    :param block: блок месяца.
    :return: сумма (может быть отрицательной); по умолчанию 0.
    """
    return _num(block.get(KEY_CARRYOVER, 0.0))


def set_carryover(block: dict, amount: float) -> None:
    """Установить входящий остаток месяца.

    :param block: блок месяца.
    :param amount: сумма (может быть отрицательной — задолженность).
    """
    block[KEY_CARRYOVER] = round(float(amount), 2)


def is_valid_budget(data) -> bool:
    """Проверить, что JSON похож на бюджет по месяцам.

    :param data: объект, полученный из json.load.
    :return: True, если структура распознана.
    """
    if not isinstance(data, dict):
        return False
    months = data.get(KEY_MONTHS)
    if not isinstance(months, dict):
        return False
    return all(isinstance(block, dict) for block in months.values())


def ensure_month(data: dict, key: str) -> Dict[str, list]:
    """Вернуть блок месяца, создав пустой при отсутствии.

    :param data: структура бюджета (изменяется на месте).
    :param key: строка месяца «YYYY-MM».
    :return: блок месяца.
    """
    data.setdefault(KEY_MONTHS, {})
    data[KEY_MONTHS].setdefault(key, empty_month_block())
    block = data[KEY_MONTHS][key]
    block.setdefault(KEY_PLANNED_INCOME, [])
    block.setdefault(KEY_PLANNED_ARTICLES, [])
    block.setdefault(KEY_ACTUAL_EXPENSES, [])
    block.setdefault(KEY_CARRYOVER, 0.0)
    return block


def month_keys(data: dict) -> List[str]:
    """Отсортированный список месяцев, известных в бюджете.

    :param data: структура бюджета.
    :return: список ключей «YYYY-MM» по возрастанию.
    """
    return sorted(data.get(KEY_MONTHS, {}))


# --- Конструкторы записей ------------------------------------------------------
def make_planned_income(source: str, amount: float) -> dict:
    """Создать запись планового дохода за месяц.

    :param source: источник дохода (например, «Зарплата»).
    :param amount: сумма в рублях.
    """
    return {KEY_SOURCE: source, KEY_AMOUNT: amount}


def set_planned_income(block: dict, source: str, amount: float) -> None:
    """Установить плановый доход по источнику, заменяя прежний.

    Ноль «удаляет» источник из плана месяца — пустые значения не
    сохраняются.

    :param block: блок месяца.
    :param source: источник дохода.
    :param amount: сумма; 0 — убрать источник из плана.
    """
    remaining = [
        entry for entry in block[KEY_PLANNED_INCOME]
        if str(entry.get(KEY_SOURCE, "")) != source
    ]
    if amount > 0:
        remaining.append(make_planned_income(source, amount))
    block[KEY_PLANNED_INCOME] = remaining


def make_planned_article(group: str, category: str, amount: float) -> dict:
    """Создать плановую сумму по подкатегории группы.

    Подкатегория обязательна: план редактируется по подкатегориям.

    :param group: группа из справочника.
    :param category: подкатегория из справочника.
    :param amount: сумма плана в рублях.
    """
    return {KEY_GROUP: group, KEY_CATEGORY: category, KEY_AMOUNT: amount}


def make_actual_expense(group: str, category: str, comment: str, amount: float,
                        spent_on: str) -> dict:
    """Создать фактический расход с датой и комментарием.

    :param group: группа из справочника.
    :param category: подкатегория из справочника.
    :param comment: комментарий к трате.
    :param amount: сумма в рублях.
    :param spent_on: полная дата траты (YYYY-MM-DD).
    """
    return {KEY_GROUP: group, KEY_CATEGORY: category, KEY_COMMENT: comment,
            KEY_AMOUNT: amount, KEY_DATE: spent_on}


def entry_label(entry: dict) -> str:
    """Человекочитаемое имя статьи записи: «Группа — Подкатегория».

    :param entry: запись плана или факта.
    """
    return f"{entry.get(KEY_GROUP, '')} — {entry.get(KEY_CATEGORY, '')}"


# --- Редактирование плана --------------------------------------------------------
def set_planned_article(block: dict, group: str, category: str, amount: float) -> None:
    """Установить плановую сумму подкатегории, заменяя прежнюю.

    Ноль «удаляет» статью из плана месяца — пустые значения не сохраняются.

    :param block: блок месяца.
    :param group: группа.
    :param category: подкатегория.
    :param amount: сумма плана; 0 — убрать статью из плана.
    """
    remaining = [
        entry for entry in block[KEY_PLANNED_ARTICLES]
        if not (str(entry.get(KEY_GROUP, "")) == group
                and str(entry.get(KEY_CATEGORY, "")) == category)
    ]
    if amount > 0:
        remaining.append(make_planned_article(group, category, amount))
    block[KEY_PLANNED_ARTICLES] = remaining


# --- Работа со статьями при удалении --------------------------------------------
def count_article_usage(data: dict, group: str, category: Optional[str] = None) -> int:
    """Сколько записей бюджета ссылаются на статью (по всем месяцам).

    Используется интерфейсом для предупреждения перед удалением группы
    или подкатегории.

    :param data: структура бюджета.
    :param group: название группы.
    :param category: подкатегория; None — вся группа.
    :return: число записей плана и факта.
    """
    count = 0
    for block in data.get(KEY_MONTHS, {}).values():
        collections = (KEY_PLANNED_ARTICLES, KEY_ACTUAL_EXPENSES)
        for collection in collections:
            for entry in block.get(collection, []):
                if not isinstance(entry, dict) or str(entry.get(KEY_GROUP, "")) != group:
                    continue
                if category is None or str(entry.get(KEY_CATEGORY, "")) == category:
                    count += 1
    return count


def relocate_article_entries(data: dict, group: str, category: Optional[str] = None) -> List[str]:
    """Перенести все записи статьи в «Прочее», чтобы данные не терялись.

    Удаляемая статья остаётся в бюджете как подкатегория группы «Прочее»
    с тем же названием: план «Жильё/Аренда» → «Прочее/Жильё·Аренда»
    при удалении группы, «Прочее/Аренда» — при удалении подкатегории.
    Возвращает перенесённые подписи (для дописывания в справочник).

    :param data: структура бюджета (изменяется на месте).
    :param group: удаляемая группа.
    :param category: удаляемая подкатегория; None — вся группа.
    :return: отсортированный список новых подкатегорий в «Прочее».
    """
    moved: set = set()
    for block in data.get(KEY_MONTHS, {}).values():
        # --- План ---
        rebuilt = []
        for entry in block.get(KEY_PLANNED_ARTICLES, []):
            if (isinstance(entry, dict) and str(entry.get(KEY_GROUP, "")) == group
                    and (category is None or str(entry.get(KEY_CATEGORY, "")) == category)):
                new_label = (f"{group}·{entry.get(KEY_CATEGORY, '')}" if category is not None
                             else str(group))
                moved.add(new_label)
                rebuilt.append(make_planned_article(KEY_UNKNOWN_GROUP, new_label,
                                                    _num(entry.get(KEY_AMOUNT))))
            else:
                rebuilt.append(entry)
        block[KEY_PLANNED_ARTICLES] = rebuilt
        # --- Факт ---
        rebuilt = []
        for entry in block.get(KEY_ACTUAL_EXPENSES, []):
            if (isinstance(entry, dict) and str(entry.get(KEY_GROUP, "")) == group
                    and (category is None or str(entry.get(KEY_CATEGORY, "")) == category)):
                new_label = (f"{group}·{entry.get(KEY_CATEGORY, '')}" if category is not None
                             else str(group))
                moved.add(new_label)
                rebuilt.append(make_actual_expense(
                    KEY_UNKNOWN_GROUP, new_label,
                    str(entry.get(KEY_COMMENT, "")), _num(entry.get(KEY_AMOUNT)),
                    str(entry.get(KEY_DATE, ""))))
            else:
                rebuilt.append(entry)
        block[KEY_ACTUAL_EXPENSES] = rebuilt
    return sorted(moved)


# --- Миграции прежних форматов ----------------------------------------------------
KEY_UNKNOWN_GROUP = "Прочее"


def _num(value) -> float:
    """Сумму записи привести к float (на случай ручной правки файла)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def migrate_flat_entries(block: dict) -> List[str]:
    """Перенести записи месяца из плоских категорий в «Прочее».

    Записи без ключа «group» (форматы CLI и Streamlit-v2 с плоскими
    категориями) переезжают в группу «Прочее» как подкатегории с прежними
    названиями: данные не теряются и остаются видны в отчёте. Возвращает
    использованные имена — вызывающий код дописывает их в справочник
    («Прочее»), чтобы записи остались выбираемыми.

    :param block: блок месяца (изменяется на месте).
    :return: отсортированный список прежних плоских категорий.
    """
    used: set = set()

    # --- План: старые записи [{category, amount}] → Прочее/<имя> ---
    kept_plan: List[dict] = []
    flat_plan: Dict[str, float] = {}
    for entry in block[KEY_PLANNED_ARTICLES]:
        if isinstance(entry, dict) and KEY_GROUP in entry:
            kept_plan.append(entry)  # уже двухуровневая запись
            continue
        if not isinstance(entry, dict):
            continue
        name = str(entry.get(KEY_CATEGORY, "")).strip() or KEY_UNKNOWN_GROUP
        used.add(name)
        flat_plan[name] = flat_plan.get(name, 0.0) + _num(entry.get(KEY_AMOUNT))
    if flat_plan:
        kept_plan += [
            make_planned_article(KEY_UNKNOWN_GROUP, name, amount)
            for name, amount in sorted(flat_plan.items()) if amount > 0
        ]
        block[KEY_PLANNED_ARTICLES] = kept_plan

    # --- Факт: старые записи [{category, name/comment, ...}] → Прочее/<имя> ---
    kept_fact: List[dict] = []
    had_flat = False
    for entry in block[KEY_ACTUAL_EXPENSES]:
        if isinstance(entry, dict) and KEY_GROUP in entry:
            kept_fact.append(entry)
            continue
        if not isinstance(entry, dict):
            continue
        had_flat = True
        name = str(entry.get(KEY_CATEGORY, "")).strip() or KEY_UNKNOWN_GROUP
        used.add(name)
        kept_fact.append(make_actual_expense(
            KEY_UNKNOWN_GROUP, name,
            str(entry.get(KEY_COMMENT, "") or entry.get(KEY_NAME, "")),
            _num(entry.get(KEY_AMOUNT)),
            str(entry.get(KEY_DATE, "")),
        ))
    if had_flat:
        block[KEY_ACTUAL_EXPENSES] = kept_fact

    return sorted(used)


def migrate_legacy_budget(data: dict) -> dict:
    """Перенести бюджет CLI-версии (план/факт в корне JSON) в новый формат.

    Два типа плановых расходов CLI (mandatory/purchases) сливаются
    по плоской категории; плоские категории уходят в группу «Прочее»
    как подкатегории с прежними названиями. Возвращает структуру
    с заполненным текущим календарным месяцем.

    :param data: словарь старого формата.
    :return: словарь нового формата.
    """
    from datetime import date

    block = empty_month_block()
    legacy_planned_income = data.get("planned_income") or []
    legacy_planned = data.get("planned_expenses") or {}
    legacy_expenses = data.get("actual_expenses") or []

    block[KEY_PLANNED_INCOME] = [
        make_planned_income(str(entry.get(KEY_SOURCE, "")), _num(entry.get(KEY_AMOUNT)))
        for entry in legacy_planned_income if isinstance(entry, dict)
    ]

    planned: Dict[Tuple[str, str], float] = {}
    for entries in legacy_planned.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            flat = str(entry.get(KEY_CATEGORY, "")).strip() or KEY_UNKNOWN
            planned[("Прочее", flat)] = planned.get(("Прочее", flat), 0.0) + _num(entry.get(KEY_AMOUNT))

    block[KEY_PLANNED_ARTICLES] = [
        make_planned_article(group, category, amount)
        for (group, category), amount in sorted(planned.items()) if amount > 0
    ]

    block[KEY_ACTUAL_EXPENSES] = [
        make_actual_expense("Прочее", flat,
                            str(entry.get(KEY_NAME, "") or entry.get(KEY_COMMENT, "")),
                            _num(entry.get(KEY_AMOUNT)),
                            str(entry.get(KEY_DATE, "")))
        for entry in legacy_expenses if isinstance(entry, dict)
        for flat in [str(entry.get(KEY_CATEGORY, "")).strip() or KEY_UNKNOWN]
    ]

    today = date.today()
    return {KEY_MONTHS: {month_key(today.year, today.month): block}}

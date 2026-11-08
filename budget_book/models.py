# -*- coding: utf-8 -*-
"""Модель данных веб-приложения «Книга доходов и расходов».

Бюджет хранится по месяцам: каждый месяц — отдельный блок, поэтому
выбор месяца сверху страницы сразу переключает и план, и отчёт.
Записи — обычные словари, сериализуемые в JSON без дополнительной магии.
Здесь собраны константы структуры, конструкторы записей и migration-хелпер
для данных CLI-версии (один общий месяц вместо набора месяцев).
"""

from typing import Dict, List, Optional, Tuple

# --- Ключи структуры бюджета ---------------------------------------------------
KEY_MONTHS = "months"                 # {«YYYY-MM»: блок месяца}

# --- Ключи блока месяца --------------------------------------------------------
KEY_PLANNED_INCOME = "planned_income"   # [{source, amount}]
KEY_PLANNED_ARTICLES = "planned_articles"  # [{category, amount}]
KEY_ACTUAL_EXPENSES = "actual_expenses"  # [{category, comment, amount, date}]

# --- Ключи записей -------------------------------------------------------------
KEY_CATEGORY = "category"
KEY_SOURCE = "source"
KEY_AMOUNT = "amount"
KEY_NAME = "name"
KEY_COMMENT = "comment"
KEY_DATE = "date"


def month_key(year: int, month: int) -> str:
    """Собрать ключ месяца «YYYY-MM» (для сортировки и ключа months).

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


def new_budget() -> dict:
    """Создать пустую структуру бюджета с единственным текущим пустым месяцем."""
    return {KEY_MONTHS: {}}


def empty_month_block() -> Dict[str, list]:
    """Создать пустой блок месяца (план доходов, план статей, факты)."""
    return {
        KEY_PLANNED_INCOME: [],
        KEY_PLANNED_ARTICLES: [],
        KEY_ACTUAL_EXPENSES: [],
    }


def is_valid_budget(data) -> bool:
    """Проверить, что загруженный JSON похож на бюджет приложения.

    Считается валидным любой словарь с ключом months, где значения —
    словари (содержимое блоков допускается неполным и достраивается).

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
    """Вернуть блок месяца в бюджете, создав пустой при отсутствии.

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


def make_planned_article(category: str, amount: float) -> dict:
    """Создать плановую сумму по статье расходов.

    У статьи в месяце ровно одна плановая сумма — сумма статьи
    за весь выбранный месяц.

    :param category: статья расхода из справочника.
    :param amount: сумма плана в рублях.
    """
    return {KEY_CATEGORY: category, KEY_AMOUNT: amount}


def make_actual_expense(category: str, comment: str, amount: float, spent_on: str) -> dict:
    """Создать фактический расход с полем даты и комментарием.

    :param category: статья расхода из справочника.
    :param comment: комментарий к трате.
    :param amount: сумма в рублях.
    :param spent_on: полная дата траты (YYYY-MM-DD).
    """
    return {KEY_CATEGORY: category, KEY_COMMENT: comment,
            KEY_AMOUNT: amount, KEY_DATE: spent_on}


# --- Ремонт дубликатов плана ---------------------------------------------------
def set_planned_article(block: dict, category: str, amount: float) -> None:
    """Установить плановую сумму статьи месяца, заменяя прежнюю.

    Ноль «удаляет» статью из плана месяца — пустые значения не сохраняются.

    :param block: блок месяца.
    :param category: статья расхода.
    :param amount: сумма плана; 0 — убрать статью из плана.
    """
    remaining = [
        entry for entry in block[KEY_PLANNED_ARTICLES]
        if str(entry.get(KEY_CATEGORY, "")) != category
    ]
    if amount > 0:
        remaining.append(make_planned_article(category, amount))
    block[KEY_PLANNED_ARTICLES] = remaining


# --- Обратная совместимость: данные CLI-версии ---------------------------------
def migrate_legacy_budget(data: dict) -> dict:
    """Перенести бюджет CLI-версии (один месяц, mandatory/purchases) в новый формат.

    CLI-версия хранила plan/факт в корне JSON. Такой файл остаётся
    читаемым: всё переносится в текущий календарный месяц; два типа
    плановых расходов сливаются в статьи, «name» расхода становится
    его комментарием. Факт-доходы CLI-версии не переносятся — в веб-
    версии поля для них нет.

    :param data: словарь старого формата (план/факт в корне).
    :return: словарь нового формата.
    """
    from datetime import date

    legacy_planned_income = data.get("planned_income") or []
    legacy_planned = data.get("planned_expenses") or {}
    legacy_expenses = data.get("actual_expenses") or []

    planned_income: List[dict] = [
        make_planned_income(str(entry.get(KEY_SOURCE, "")), _num(entry.get(KEY_AMOUNT)))
        for entry in legacy_planned_income if isinstance(entry, dict)
    ]

    # mandatory и purchases сливались по категории
    per_category: Dict[str, float] = {}
    for entries in legacy_planned.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                category = str(entry.get(KEY_CATEGORY, ""))
                per_category[category] = per_category.get(category, 0.0) + _num(entry.get(KEY_AMOUNT))

    actual_expenses: List[dict] = []
    for entry in legacy_expenses:
        if not isinstance(entry, dict):
            continue
        actual_expenses.append(make_actual_expense(
            str(entry.get(KEY_CATEGORY, "")),
            str(entry.get(KEY_NAME, "") or entry.get(KEY_COMMENT, "")),
            _num(entry.get(KEY_AMOUNT)),
            str(entry.get(KEY_DATE, "")),
        ))

    block = empty_month_block()
    block[KEY_PLANNED_INCOME] = planned_income
    block[KEY_PLANNED_ARTICLES] = [
        make_planned_article(category, amount) for category, amount in sorted(per_category.items())
        if amount > 0
    ]
    block[KEY_ACTUAL_EXPENSES] = actual_expenses

    today = date.today()
    return {KEY_MONTHS: {month_key(today.year, today.month): block}}


def _num(value) -> float:
    """Сумму записи привести к float (на случай ручной правки файла)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def month_of_date(iso_date: str) -> Optional[str]:
    """Ключ месяца из полной даты «YYYY-MM-DD».

    :param iso_date: дата-строка.
    :return: «YYYY-MM» или None, если дата не распознана.
    """
    if not iso_date:
        return None
    return "-".join(iso_date.split("-")[:2])

# -*- coding: utf-8 -*-
"""Модели данных «Книги доходов и расходов».

Данные приложения хранятся в виде обычных словарей, которые
сериализуются в JSON без дополнительной магии. Здесь собраны
константы структуры, конструкторы записей и небольшие хелперы.
"""

from typing import Optional

# --- Ключи на верхнем уровне структуры бюджета -------------------------------
KEY_PLANNED_INCOME = "planned_income"
KEY_PLANNED_EXPENSES = "planned_expenses"
KEY_ACTUAL_INCOME = "actual_income"
KEY_ACTUAL_EXPENSES = "actual_expenses"

# --- Типы плановых расходов ---------------------------------------------------
KEY_MANDATORY = "mandatory"   # обязательные платежи (аренда, ЖКХ, связь)
KEY_PURCHASES = "purchases"   # плановые покупки (техника, отпуск)

EXPENSE_KINDS = (KEY_MANDATORY, KEY_PURCHASES)

KIND_LABELS = {
    KEY_MANDATORY: "Обязательные платежи (mandatory)",
    KEY_PURCHASES: "Плановые покупки (purchases)",
}

# Категория, под которую попадают фактические расходы, чья категория
# не встречается ни в одном из плановых списков.
OTHER_KIND_LABEL = "Прочие (вне плана)"


def new_budget() -> dict:
    """Создать пустую структуру бюджета.

    :return: словарь с пустыми списками доходов и расходов.
    """
    return {
        KEY_PLANNED_INCOME: [],
        KEY_PLANNED_EXPENSES: {kind: [] for kind in EXPENSE_KINDS},
        KEY_ACTUAL_INCOME: [],
        KEY_ACTUAL_EXPENSES: [],
    }


def is_valid_budget(data) -> bool:
    """Проверить, что загруженный JSON имеет ожидаемую структуру.

    :param data: объект, полученный из json.load.
    :return: True, если структура похожа на бюджет приложения.
    """
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get(KEY_PLANNED_INCOME), list):
        return False
    if not isinstance(data.get(KEY_ACTUAL_INCOME), list):
        return False
    if not isinstance(data.get(KEY_ACTUAL_EXPENSES), list):
        return False
    planned_expenses = data.get(KEY_PLANNED_EXPENSES)
    if not isinstance(planned_expenses, dict):
        return False
    return all(isinstance(planned_expenses.get(kind), list) for kind in EXPENSE_KINDS)


# --- Конструкторы записей ------------------------------------------------------
def make_planned_income(source: str, amount: float) -> dict:
    """Создать запись планового дохода.

    :param source: источник дохода (например, «Зарплата»).
    :param amount: сумма в рублях.
    :return: словарь-запись.
    """
    return {"source": source, "amount": amount}


def make_planned_expense(kind: str, category: str, name: str, amount: float) -> dict:
    """Создать запись планового расхода одного из двух типов.

    :param kind: тип расхода — KEY_MANDATORY или KEY_PURCHASES.
    :param category: категория расхода (например, «Аренда»).
    :param name: название позиции (например, «Квартира в центре»).
    :param amount: сумма в рублях.
    :return: словарь-запись.
    """
    if kind not in EXPENSE_KINDS:
        raise ValueError(f"Неизвестный тип планового расхода: {kind!r}")
    return {"category": category, "name": name, "amount": amount}


def make_actual_income(category: str, name: str, amount: float, received_on: str) -> dict:
    """Создать запись фактического дохода.

    :param category: категория дохода (обычно совпадает с источником плана).
    :param name: название поступления.
    :param amount: сумма в рублях.
    :param received_on: дата поступления (YYYY-MM-DD).
    :return: словарь-запись.
    """
    return {"category": category, "name": name, "amount": amount, "date": received_on}


def make_actual_expense(category: str, name: str, amount: float, spent_on: str) -> dict:
    """Создать запись фактического расхода.

    :param category: категория расхода.
    :param name: название траты.
    :param amount: сумма в рублях.
    :param spent_on: дата траты (YYYY-MM-DD).
    :return: словарь-запись.
    """
    return {"category": category, "name": name, "amount": amount, "date": spent_on}


def find_planned_kind(data: dict, category: str) -> Optional[str]:
    """Определить тип планового расхода по названию категории.

    Фактический расход не несёт информации об обязательности платежа,
    поэтому тип восстанавливается по совпадению категории с плановой.

    :param data: структура бюджета.
    :param category: название категории расхода.
    :return: KEY_MANDATORY или KEY_PURCHASES, иначе None.
    """
    planned = data[KEY_PLANNED_EXPENSES]
    for kind in EXPENSE_KINDS:
        for entry in planned[kind]:
            if str(entry.get("category", "")).lower() == category.lower():
                return kind
    return None

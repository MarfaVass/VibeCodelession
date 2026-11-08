# -*- coding: utf-8 -*-
"""Расчёт план-факта за выбранный месяц по группам и подкатегориям.

Модуль не знает про интерфейс: принимает структуру бюджета и ключ
месяца, возвращает строки групп (план, факт, разница, процент) с
раскрытием подкатегорий. format_report() оставлен текстовым — им
пользуется smoke-тест; Streamlit печатает те же данные таблицей.
"""

from typing import Dict, List, Optional

import categories
import models

PERCENT_DASH = "—"
NO_DATA = "(нет данных)"
GROUP_COLUMN = "Группа"
SUB_COLUMN = "Подкатегория"
NO_SUBCATEGORY_LABEL = "(без подкатегорий)"  # план/факт, записанный на группу целиком


# --- Форматирование -----------------------------------------------------------
def format_money(value: float) -> str:
    """Отформатировать сумму по-русски: 80000 -> «80 000,00»."""
    whole, frac = f"{value:,.2f}".split(".")
    return whole.replace(",", " ") + "," + frac


def format_percent(plan: float, fact: float) -> str:
    """Процент расхода от плана; при нулевом плане — прочерк (без деления на 0)."""
    if plan == 0:
        return PERCENT_DASH
    return f"{fact / plan * 100:.1f}%"


def _as_float(value) -> float:
    """Сумму записи привести к float (на случай ручной правки файла)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# --- Строки статей месяца -------------------------------------------------------
def _empty_totals() -> Dict[str, float]:
    """Шаблон накопительных сумм: {plan, fact}."""
    return {"plan": 0.0, "fact": 0.0}


def group_rows(data: dict, month: str) -> List[Dict]:
    """Собрать план-факт по группам за месяц (для диаграмм и сводки).

    Функции подкатегорий агрегируются в группу. Порядок групп — как
    в справочнике data/categories.json; группы вне справочника — в конце
    по алфавиту. Группы без плана и без факта не выводятся.

    :param data: структура бюджета.
    :param month: ключ месяца «YYYY-MM».
    :return: список словарей {group, plan, fact, diff, percent}.
    """
    block = models.ensure_month(data, month)
    totals: Dict[str, Dict[str, float]] = {}
    for entry in block[models.KEY_PLANNED_ARTICLES]:
        group = str(entry.get(models.KEY_GROUP, ""))
        totals.setdefault(group, _empty_totals())["plan"] += _as_float(entry.get(models.KEY_AMOUNT))
    for entry in block[models.KEY_ACTUAL_EXPENSES]:
        group = str(entry.get(models.KEY_GROUP, ""))
        totals.setdefault(group, _empty_totals())["fact"] += _as_float(entry.get(models.KEY_AMOUNT))

    catalog = categories.load_categories()
    ordered = [group for group in catalog if group in totals]
    ordered += sorted(group for group in totals if group not in catalog)

    rows: List[Dict] = []
    for group in ordered:
        plan, fact = totals[group]["plan"], totals[group]["fact"]
        if plan == 0 and fact == 0:
            continue
        rows.append({
            "group": group,
            "plan": plan,
            "fact": fact,
            "diff": round(plan - fact, 2),
            "percent": fact / plan if plan > 0 else None,
        })
    return rows


def sub_rows(data: dict, month: str, group: str) -> List[Dict]:
    """Строки план-факт подкатегорий одной группы (раскрытие в отчёте).

    Порядок — как в справочнике; статьи вне справочника — в конце по
    алфавиту. Подкатегории без плана и без факта не выводятся.

    :param data: структура бюджета.
    :param month: ключ месяца «YYYY-MM».
    :param group: название группы.
    :return: список словарей {sub, plan, fact, diff, percent}.
    """
    block = models.ensure_month(data, month)
    totals: Dict[str, Dict[str, float]] = {}
    for entry in block[models.KEY_PLANNED_ARTICLES]:
        if str(entry.get(models.KEY_GROUP, "")) != group:
            continue
        sub = str(entry.get(models.KEY_CATEGORY, ""))
        totals.setdefault(sub, _empty_totals())["plan"] += _as_float(entry.get(models.KEY_AMOUNT))
    for entry in block[models.KEY_ACTUAL_EXPENSES]:
        if str(entry.get(models.KEY_GROUP, "")) != group:
            continue
        sub = str(entry.get(models.KEY_CATEGORY, ""))
        totals.setdefault(sub, _empty_totals())["fact"] += _as_float(entry.get(models.KEY_AMOUNT))

    catalog = categories.load_categories()
    known = [sub for sub in catalog.get(group, []) if sub in totals]
    unknown = sorted(sub for sub in totals if sub not in catalog.get(group, []))

    rows: List[Dict] = []
    for sub in known + unknown:
        plan, fact = totals[sub]["plan"], totals[sub]["fact"]
        if plan == 0 and fact == 0:
            continue
        rows.append({
            "sub": sub,
            "plan": plan,
            "fact": fact,
            "diff": round(plan - fact, 2),
            "percent": fact / plan if plan > 0 else None,
        })
    return rows


def income_total(data: dict, month: str) -> float:
    """Суммарный плановый доход за месяц.

    :param data: структура бюджета.
    :param month: ключ месяца «YYYY-MM».
    """
    block = models.ensure_month(data, month)
    return sum(_as_float(entry.get(models.KEY_AMOUNT)) for entry in block[models.KEY_PLANNED_INCOME])


def expenses_totals(data: dict, month: str) -> Dict[str, float]:
    """Итоги расходов за месяц и остаток (плановый и фактический).

    :param data: структура бюджета.
    :param month: ключ месяца «YYYY-MM».
    :return: {expenses_plan, expenses_fact, balance_plan, balance_fact}.
    """
    rows = group_rows(data, month)
    expenses_plan = sum(row["plan"] for row in rows)
    expenses_fact = sum(row["fact"] for row in rows)
    return {
        "expenses_plan": expenses_plan,
        "expenses_fact": expenses_fact,
        "balance_plan": income_total(data, month) - expenses_plan,
        "balance_fact": -expenses_fact,  # факт-доходов в интерфейсе нет
    }


# --- Текстовый отчёт -------------------------------------------------------------
def format_totals_line(label: str, plan: Optional[float], fact: Optional[float] = None) -> str:
    """Сформатировать одну строку итогов «план/факт».

    :param label: название строки итога.
    :param plan: суммарный план (None — прочерк).
    :param fact: суммарный факт (None — прочерк, если фактов в разрезе нет).
    """
    plan_text = format_money(plan) if plan is not None else PERCENT_DASH
    fact_text = format_money(fact) if fact is not None else PERCENT_DASH
    return f"  {label.ljust(34)} план: {plan_text:>12} | факт: {fact_text:>12}"


def _format_row(label: str, row: Dict, width: int, indent: int = 0) -> str:
    """Строка план-факт (группы или подкатегории) для текстового отчёта."""
    percent = (PERCENT_DASH if row["percent"] is None
               else f"{row['percent'] * 100:.1f}%")
    return ("  " + " " * indent
            + label.ljust(width - indent) + f" | {format_money(row['plan']):>12} | "
            f"{format_money(row['fact']):>12} | {format_money(row['diff']):>12} | {percent:>10}")


def format_report(data: dict, month: str) -> str:
    """Собрать полный текст отчёта «План-факт» за месяц.

    Группы с раскрытием подкатегорий; пустые группы (без плана и факта)
    не выводятся.

    :param data: структура бюджета.
    :param month: ключ месяца «YYYY-MM».
    :return: готовый к печати отчёт.
    """
    totals = expenses_totals(data, month)
    parts = [
        f"ОТЧЁТ «ПЛАН-ФАКТ» — {month}",
        "=" * 62,
        "Итоги:",
    ]
    parts.append(format_totals_line("Доходы (план)", income_total(data, month)))
    parts.append(format_totals_line("Расходы — всего", totals["expenses_plan"], totals["expenses_fact"]))
    parts.append(format_totals_line("Остаток (доходы - расходы)", totals["balance_plan"], totals["balance_fact"]))
    parts.append("")
    parts.append("План-факт по группам (с раскрытием подкатегорий):")

    rows = group_rows(data, month)
    if not rows:
        parts.append(f"  {NO_DATA}")
        return "\n".join(parts)

    width = len(GROUP_COLUMN)
    for row in rows:
        width = max(width, len(row["group"]))
        for sub in sub_rows(data, month, row["group"]):
            width = max(width, 3 + len(sub["sub"]))
    parts.append(f"  {GROUP_COLUMN.ljust(width)} | {'План':>12} | {'Факт':>12} | "
                 f"{'Разница':>12} | {'% от плана':>10}")
    parts.append("  " + "-" * (width + 62))
    for row in rows:
        parts.append(_format_row(row["group"], row, width))
        for sub in sub_rows(data, month, row["group"]):
            sub_name = sub["sub"] or NO_SUBCATEGORY_LABEL
            parts.append(_format_row(f"→ {sub_name}", sub, width, indent=3))
    return "\n".join(parts)

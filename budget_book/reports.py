# -*- coding: utf-8 -*-
"""Расчёт план-факта за выбранный месяц и формирование таблицы отчёта.

Модуль не знает про интерфейс: принимает структуру бюджета и ключ
месяца, возвращает строки статей (план, факт, разница, процент) и
итоги. format_report() оставлен текстовым — им пользуется smoke-тест,
а Streamlit печатает те же данные таблицей.
"""

from typing import Dict, List, Optional

import categories
import models

PERCENT_DASH = "—"
NO_DATA = "(нет данных)"
ARTICLE_COLUMN = "Статья"
NO_PLANNED_INCOME_NOTE = "Плановый доход за месяц не задан."
UNKNOWN_ARTICLE_LABEL = "Вне справочника"


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
def article_rows(data: dict, month: str) -> List[Dict]:
    """Собрать строки план-факта по статьям расходов за месяц.

    Порядок статей — как в справочнике data/categories.json; статьи вне
    справочника печатаются после, по алфавиту. Статьи без плана и без
    факта не выводятся.

    :param data: структура бюджета.
    :param month: ключ месяца «YYYY-MM».
    :return: список словарей {article, plan, fact, diff, percent}.
    """
    block = models.ensure_month(data, month)
    totals: Dict[str, Dict[str, float]] = {}
    for entry in block[models.KEY_PLANNED_ARTICLES]:
        article = str(entry.get(models.KEY_CATEGORY, ""))
        row = totals.setdefault(article, {"plan": 0.0, "fact": 0.0})
        row["plan"] += _as_float(entry.get(models.KEY_AMOUNT))
    for entry in block[models.KEY_ACTUAL_EXPENSES]:
        article = str(entry.get(models.KEY_CATEGORY, ""))
        row = totals.setdefault(article, {"plan": 0.0, "fact": 0.0})
        row["fact"] += _as_float(entry.get(models.KEY_AMOUNT))

    catalog = categories.load_categories()
    ordered = [article for article in catalog if article in totals]
    ordered += sorted(article for article in totals if article not in catalog)

    rows: List[Dict] = []
    for article in ordered:
        plan, fact = totals[article]["plan"], totals[article]["fact"]
        if plan == 0 and fact == 0:
            continue  # статью без плана и без факта не выводим
        rows.append({
            "article": article,
            "plan": plan,
            "fact": fact,
            "diff": round(plan - fact, 2),
            "percent": fact / plan if plan > 0 else None,  # доля факта от плана
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
    rows = article_rows(data, month)
    expenses_plan = sum(row["plan"] for row in rows)
    expenses_fact = sum(row["fact"] for row in rows)
    return {
        "expenses_plan": expenses_plan,
        "expenses_fact": expenses_fact,
        "balance_plan": income_total(data, month) - expenses_plan,
        "balance_fact": -expenses_fact,  # факт-доходов в интерфейсе нет
    }


def format_totals_line(label: str, plan: Optional[float], fact: float) -> str:
    """Сформатировать одну строку итогов «план/факт».

    :param label: название строки итога.
    :param plan: суммарный план (None — прочерк).
    :param fact: суммарный факт.
    """
    plan_text = format_money(plan) if plan is not None else PERCENT_DASH
    return f"  {label.ljust(34)} план: {plan_text:>12} | факт: {format_money(fact):>12}"


def format_report(data: dict, month: str) -> str:
    """Собрать полный текст отчёта «План-факт» за месяц.

    :param data: структура бюджета.
    :param month: ключ месяца «YYYY-MM».
    :return: готовый к печати отчёт.
    """
    totals = expenses_totals(data, month)
    income_plan = income_total(data, month)
    parts = [
        f"ОТЧЁТ «ПЛАН-ФАКТ» — {month}",
        "=" * 62,
        "Итоги:",
    ]
    parts.append(format_totals_line("Доходы (план)", income_plan, 0.0))
    parts.append(format_totals_line("Расходы — всего", totals["expenses_plan"], totals["expenses_fact"]))
    parts.append(format_totals_line("Остаток (доходы - расходы)", totals["balance_plan"], totals["balance_fact"]))
    parts.append("")
    parts.append("План-факт по статьям:")
    rows = article_rows(data, month)
    if not rows:
        parts.append(f"  {NO_DATA}")
        return "\n".join(parts)
    width = max(len(ARTICLE_COLUMN), max(len(row["article"]) for row in rows))
    parts.append(f"  {ARTICLE_COLUMN.ljust(width)} | {'План':>12} | {'Факт':>12} | "
                 f"{'Разница':>12} | {'% от плана':>10}")
    parts.append("  " + "-" * (width + 62))
    for row in rows:
        percent = f"{row['percent'] * 100:.1f}%" if row["percent"] is not None else PERCENT_DASH
        parts.append(
            f"  {row['article'].ljust(width)} | {format_money(row['plan']):>12} | "
            f"{format_money(row['fact']):>12} | {format_money(row['diff']):>12} | {percent:>10}"
        )
    return "\n".join(parts)

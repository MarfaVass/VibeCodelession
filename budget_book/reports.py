# -*- coding: utf-8 -*-
"""Расчёт план-факта и формирование текстового отчёта.

Модуль не знает про ввод-вывод консоли, кроме print_report: он принимает
структуру бюджета и возвращает/печатает готовый отчёт, что удобно и для
меню, и для smoke-теста.
"""

from typing import Dict, List, Optional

import categories
import models

PERCENT_DASH = "—"
NO_DATA = "(нет данных)"
TABLE_HEADER = ("Категория", "План", "Факт", "Выполнение")
OTHER_CATEGORY_LABEL = "Прочие"


# --- Форматирование -----------------------------------------------------------
def format_money(value: float) -> str:
    """Отформатировать сумму по-русски: 80000 -> «80 000,00»."""
    whole, frac = f"{value:,.2f}".split(".")
    return whole.replace(",", " ") + "," + frac


def format_percent(plan: float, fact: float) -> str:
    """Процент выполнения плана; при нулевом плане — прочерк (без деления на 0)."""
    if plan == 0:
        return PERCENT_DASH
    return f"{fact / plan * 100:.1f}%"


def _as_float(value) -> float:
    """Привести сумму записи к float (на случай ручной правки файла)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# --- Сборка строк по категориям -----------------------------------------------
def _merge_category(rows: Dict[str, Dict[str, float]], category: str, column: str, amount: float) -> None:
    """Добавить сумму в накопительную строку категории (plan или fact)."""
    row = rows.setdefault(category.strip() or OTHER_CATEGORY_LABEL, {"plan": 0.0, "fact": 0.0})
    row[column] += amount


def income_rows(data: dict) -> List[Dict]:
    """Собрать строки «план/факт» по категориям (источникам) доходов.

    :param data: структура бюджета.
    :return: список словарей {category, plan, fact}, отсортированный по категории.
    """
    rows: Dict[str, Dict[str, float]] = {}
    for entry in data[models.KEY_PLANNED_INCOME]:
        _merge_category(rows, str(entry.get("source", "")), "plan", _as_float(entry.get("amount")))
    for entry in data[models.KEY_ACTUAL_INCOME]:
        _merge_category(rows, str(entry.get("category", "")), "fact", _as_float(entry.get("amount")))
    return sorted(
        ({"category": category, **row} for category, row in rows.items()),
        key=lambda row: row["category"],
    )


def expense_rows(data: dict) -> List[Dict]:
    """Собрать строки «план/факт» по категориям расходов.

    В план попадают обе разновидности плановых расходов
    (mandatory и purchases), в факт — все фактические траты.

    Порядок строк — как в справочнике data/categories.json;
    категории вне справочника печатаются после, по алфавиту.
    Категории без плана и без факта не выводятся.

    :param data: структура бюджета.
    :return: список словарей {category, plan, fact}.
    """
    rows: Dict[str, Dict[str, float]] = {}
    for kind in models.EXPENSE_KINDS:
        for entry in data[models.KEY_PLANNED_EXPENSES][kind]:
            _merge_category(rows, str(entry.get("category", "")), "plan", _as_float(entry.get("amount")))
    for entry in data[models.KEY_ACTUAL_EXPENSES]:
        _merge_category(rows, str(entry.get("category", "")), "fact", _as_float(entry.get("amount")))
    used = [row for row in rows.items() if row[1]["plan"] > 0 or row[1]["fact"] > 0]
    catalog = categories.load_categories()
    ordered = [
        {"category": name, **values} for name, values in used if name in catalog
    ]
    ordered += sorted(
        ({"category": name, **values} for name, values in used if name not in catalog),
        key=lambda row: row["category"],
    )
    return [
        {"category": row["category"], "plan": row["plan"], "fact": row["fact"]}
        for row in ordered
    ]


def _format_table(rows: List[Dict]) -> str:
    """Сформатировать таблицу категорий: план / факт / процент выполнения."""
    name_width = max(
        [len(TABLE_HEADER[0])] + [len(row["category"]) for row in rows] + [len(NO_DATA)]
    )
    lines = [
        f"  {TABLE_HEADER[0].ljust(name_width)} | {TABLE_HEADER[1]:>12} | "
        f"{TABLE_HEADER[2]:>12} | {TABLE_HEADER[3]:>10}"
    ]
    lines.append("  " + "-" * (name_width + 44))
    if not rows:
        lines.append(f"  {NO_DATA.ljust(name_width)}")
        return "\n".join(lines)
    for row in rows:
        lines.append(
            f"  {row['category'].ljust(name_width)} | {format_money(row['plan']):>12} | "
            f"{format_money(row['fact']):>12} | {format_percent(row['plan'], row['fact']):>10}"
        )
    return "\n".join(lines)


# --- Итоги ---------------------------------------------------------------------
def compute_totals(data: dict) -> Dict[str, Dict[str, float]]:
    """Рассчитать итоги план/факт: доходы, расходы (по типам), остаток.

    Фактические расходы, чья категория не встречается среди плановых,
    попадают в «Прочие» (план 0, поэтому процент — прочерк).

    :param data: структура бюджета.
    :return: словарь вида {«income»: {plan, fact}, «mandatory»: {...}, …}.
    """
    income_plan = sum(_as_float(e.get("amount")) for e in data[models.KEY_PLANNED_INCOME])
    income_fact = sum(_as_float(e.get("amount")) for e in data[models.KEY_ACTUAL_INCOME])

    plan_by_kind = {kind: 0.0 for kind in models.EXPENSE_KINDS}
    for kind in models.EXPENSE_KINDS:
        plan_by_kind[kind] = sum(
            _as_float(e.get("amount")) for e in data[models.KEY_PLANNED_EXPENSES][kind]
        )
    expenses_plan = sum(plan_by_kind.values())

    fact_by_kind = {kind: 0.0 for kind in models.EXPENSE_KINDS}
    fact_by_kind["other"] = 0.0
    for entry in data[models.KEY_ACTUAL_EXPENSES]:
        kind = models.find_planned_kind(data, str(entry.get("category", "")))
        bucket = kind if kind is not None else "other"
        fact_by_kind[bucket] += _as_float(entry.get("amount"))
    expenses_fact = sum(fact_by_kind.values())

    return {
        "income": {"plan": income_plan, "fact": income_fact},
        "expenses": {"plan": expenses_plan, "fact": expenses_fact},
        models.KEY_MANDATORY: {"plan": plan_by_kind[models.KEY_MANDATORY], "fact": fact_by_kind[models.KEY_MANDATORY]},
        models.KEY_PURCHASES: {"plan": plan_by_kind[models.KEY_PURCHASES], "fact": fact_by_kind[models.KEY_PURCHASES]},
        "other": {"plan": 0.0, "fact": fact_by_kind["other"]},  # план у «Прочих» всегда 0
        "balance": {"plan": income_plan - expenses_plan, "fact": income_fact - expenses_fact},
    }


def format_totals_line(label: str, totals: Dict[str, float]) -> str:
    """Сформатировать одну строку итогов «план/факт».

    :param label: название строки итога.
    :param totals: словарь {plan, fact} (ключ «plan» может отсутствовать).
    """
    plan_text = format_money(totals["plan"]) if "plan" in totals else PERCENT_DASH
    return f"  {label.ljust(34)} план: {plan_text:>12} | факт: {format_money(totals['fact']):>12}"


def format_report(data: dict) -> str:
    """Собрать полный текст отчёта «План-факт».

    :param data: структура бюджета.
    :return: готовый к печати отчёт.
    """
    totals = compute_totals(data)
    parts = ["ОТЧЁТ «ПЛАН-ФАКТ»", "=" * 62, "Итоги:"]
    parts.append(format_totals_line("Доходы", totals["income"]))
    parts.append(format_totals_line("Расходы — всего", totals["expenses"]))
    parts.append(format_totals_line("  " + models.KIND_LABELS[models.KEY_MANDATORY], totals[models.KEY_MANDATORY]))
    parts.append(format_totals_line("  " + models.KIND_LABELS[models.KEY_PURCHASES], totals[models.KEY_PURCHASES]))
    if totals["other"]["fact"] > 0:
        parts.append(format_totals_line("  " + models.OTHER_KIND_LABEL, totals["other"]))
    parts.append(format_totals_line("Остаток (доходы - расходы)", totals["balance"]))
    parts.append("")
    parts.append("Доходы по категориям:")
    parts.append(_format_table(income_rows(data)))
    parts.append("")
    parts.append("Расходы по категориям:")
    parts.append(_format_table(expense_rows(data)))
    return "\n".join(parts)


def print_report(data: dict) -> None:
    """Напечатать отчёт в консоль.

    :param data: структура бюджета.
    """
    print(format_report(data))

"""Сценарий «Отчет о продажах»: парсинг CSV, расчет показателей, контекст PDF.

Модуль не зависит от Tkinter — GUI только передает путь к файлу и флаги
разделов. Выручка рассчитывается как цена, умноженная на количество
единиц; отчет НЕ рассчитывает прибыль, маржинальность, динамику продаж,
скидки и возвраты: во входном формате (product, price, qty) таких
колонок нет.

Дубли: строки с одинаковым названием товара (после обрезки краевых
пробелов) агрегируются — количества и выручка суммируются, в колонке
«Цена» таблицы показывается средняя цена (выручка / количество). Одно и
то же правило применяется к таблице, долям, рейтингам и диаграмме,
поэтому все числа отчета взаимно согласованы.

Денежные величины считаются в Decimal; некорректные строки CSV
пропускаются с сохранением причины (номер строки + описание), а не
останавливают загрузку.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from common import pdf_output
from common.csv_io import read_csv_rows
from common.errors import DataError
from common.numfmt import format_money, format_percent, format_qty

REQUIRED_COLUMNS = ("product", "price", "qty")

# Флаги разделов отчета; GUI строит чекбоксы из OPTION_LABELS.
OPTIONS = ("totals", "table", "shares", "rank_revenue", "rank_qty", "chart")

OPTION_LABELS = {
    "totals": "Общая выручка и количество проданных единиц",
    "table": "Товары: цена, количество, выручка",
    "shares": "Доля каждого товара в общей выручке",
    "rank_revenue": "Рейтинг товаров по выручке",
    "rank_qty": "Рейтинг по количеству проданных единиц",
    "chart": "Диаграмма выручки",
}

MINIMAL_REPORT_OPTIONS = ("totals", "table")

TOP_CHART_LIMIT = 10  # не более 10 товаров на диаграмме, остальные — «Остальные»


def check_sales_row(row_number: int, product: str, price_raw: str,
                    qty_raw: str) -> str | None:
    """Проверяет строку CSV; возвращает причину пропуска или None.

    Полностью пустые строки пропускаются молча (лишние переводы строк).
    """
    if not product and not price_raw and not qty_raw:
        return None  # заглушка — пустая строка, без причины
    if not product:
        return "не указано название товара (колонка 'product')"
    try:
        price = Decimal(price_raw.replace(",", "."))
    except InvalidOperation:
        return f"цена «{price_raw}» — не число"
    if not price.is_finite():
        return f"цена «{price_raw}» — не корректное число (NaN или Infinity)"
    if price <= 0:
        return f"цена должна быть больше нуля (сейчас {price_raw})"
    try:
        qty = Decimal(qty_raw.replace(",", "."))
    except InvalidOperation:
        return f"количество «{qty_raw}» — не число"
    if not qty.is_finite():
        return f"количество «{qty_raw}» — не корректное число (NaN или Infinity)"
    if qty != qty.to_integral_value():
        return f"количество должно быть целым числом (сейчас {qty_raw})"
    if qty < 0:
        return "количество не может быть отрицательным"
    return None


def load_sales(path) -> dict:
    """Читает и парсит CSV о продажах, возвращая словарь данных.

    Ключи: items (валидные строки: name, price, qty в Decimal),
    skipped (список {"row", "reason"}), source_name (имя файла).
    """
    fieldnames, raw_rows = read_csv_rows(path)

    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise DataError(
            "В CSV-файле отсутствуют обязательные колонки: "
            f"{', '.join(missing)}.\n"
            "Ожидается заголовок: product,price,qty"
        )

    items: list[dict] = []
    skipped: list[dict] = []
    for row_number, row in enumerate(raw_rows, start=2):
        product = (row.get("product") or "").strip()
        price_raw = (row.get("price") or "").strip()
        qty_raw = (row.get("qty") or "").strip()
        if not product and not price_raw and not qty_raw:
            continue  # полностью пустая строка — не считается ошибкой
        reason = check_sales_row(row_number, product, price_raw, qty_raw)
        if reason is not None:
            skipped.append({"row": row_number, "reason": reason})
            continue
        items.append({
            "name": product,
            "price": Decimal(price_raw.replace(",", ".")),
            "qty": Decimal(qty_raw.replace(",", ".")),
        })

    if not items:
        raise DataError(
            "CSV-файл не содержит ни одной корректно заполненной "
            "товарной строки."
        )

    return {"items": items, "skipped": skipped, "source_name": Path(path).name}


def aggregate_items(items: list[dict]) -> list[dict]:
    """Агрегирует по названию товара (см. докстринг модуля).

    Порядок строк — по первому появлению названия в файле.
    """
    merged: dict[str, dict] = {}
    for item in items:
        slot = merged.setdefault(
            item["name"],
            {"name": item["name"], "qty": Decimal("0"), "revenue": Decimal("0")},
        )
        slot["qty"] += item["qty"]
        slot["revenue"] += item["price"] * item["qty"]
    for slot in merged.values():
        slot["avg_price"] = (
            slot["revenue"] / slot["qty"] if slot["qty"] > 0 else None
        )
    return list(merged.values())


def _ranked(by: str, rows: list[dict]) -> list[dict]:
    """Сортировка по убыванию поля `by`; при равенстве — по названию."""
    ordered = sorted(rows, key=lambda row: (-row[by], row["name"]))
    return [
        {"place": index, "name": row["name"], "value": row[by]}
        for index, row in enumerate(ordered, start=1)
    ]


def build_report(sales: dict, options: dict) -> dict:
    """Рассчитывает показатели и возвращает контекст для шаблона.

    В контекст попадают только выбранные в options разделы
    (все флаги sales_report.OPTIONS).
    """
    if not any(options.get(option) for option in OPTIONS):
        raise DataError(
            "Не выбран ни один раздел отчета.\n"
            "Отметьте хотя бы один чекбокс или нажмите «Выбрать все»."
        )

    selected = {option: bool(options.get(option)) for option in OPTIONS}
    rows = aggregate_items(sales["items"])
    total_revenue = sum((row["revenue"] for row in rows), Decimal("0"))
    total_qty = sum((row["qty"] for row in rows), Decimal("0"))
    shares_available = total_revenue > 0

    context: dict = {
        "generated_date": date.today().strftime("%d.%m.%Y"),
        "source_name": sales["source_name"],
        "skipped_count": len(sales.get("skipped", [])),
        "options": selected,
        "shares_available": shares_available,
        "shares_warning": (
            "Доли недоступны: общая выручка равна нулю, деление на ноль "
            "не выполнялось."
            if not shares_available else ""
        ),
    }

    if selected["totals"]:
        context["totals"] = {
            "revenue": format_money(total_revenue),
            "qty": format_qty(total_qty),
        }

    if selected["table"]:
        # Таблица — в порядке первого появления товара в файле.
        context["table_rows"] = [
            {
                "name": row["name"],
                "price": (
                    format_money(row["avg_price"])
                    if row["avg_price"] is not None else "—"
                ),
                "qty": format_qty(row["qty"]),
                "revenue": format_money(row["revenue"]),
            }
            for row in rows
        ]

    if selected["shares"]:
        if not shares_available:
            # Доли не строятся вовсе: деление на ноль не выполнялось.
            context["shares_rows"] = []
        else:
            context["shares_rows"] = [
                {
                    "name": row["name"],
                    "revenue": format_money(row["revenue"]),
                    "share": format_percent(row["revenue"] * 100 / total_revenue),
                    "share_width": float(row["revenue"] * 100 / total_revenue),
                }
                for row in rows
            ]

    if selected["rank_revenue"]:
        context["rank_revenue_rows"] = [
            {**row, "value": format_money(row["value"])}
            for row in _ranked("revenue", rows)
        ]

    if selected["rank_qty"]:
        context["rank_qty_rows"] = [
            {**row, "value": format_qty(row["value"])}
            for row in _ranked("qty", rows)
        ]

    if selected["chart"]:
        context["chart_bars"] = _chart_bars(rows)
        context["chart_limits"] = TOP_CHART_LIMIT

    return context


def _chart_bars(rows: list[dict]) -> list[dict]:
    """Полосы диаграммы: ширина от максимальной выручки; топ-10 + «Остальные»."""
    ordered = sorted(rows, key=lambda row: (-row["revenue"], row["name"]))
    top = ordered[:TOP_CHART_LIMIT]
    others = ordered[TOP_CHART_LIMIT:]
    max_revenue = top[0]["revenue"] if top else Decimal("0")

    def width(revenue: Decimal) -> float:
        if max_revenue <= 0:
            return 0.0
        # «Остальные» — сумма нескольких товаров и может превышать максимум
        # одной полосы; ограничиваем ширину полосы 100 % (число рядом —
        # фактическая сумма, а не масштаб).
        return min(100.0, float(revenue * 100 / max_revenue))

    bars = [
        {"name": row["name"], "value": format_money(row["revenue"]),
         "width": width(row["revenue"])}
        for row in top
    ]
    if others:
        others_revenue = sum((row["revenue"] for row in others), Decimal("0"))
        bars.append({
            "name": f"Остальные ({len(others)} шт.)",
            "value": format_money(others_revenue),
            "width": width(others_revenue),
        })
    return bars


def create_sales_pdf(sales: dict, options: dict) -> Path:
    """Создает PDF-отчет и возвращает путь к файлу."""
    context = build_report(sales, options)
    return pdf_output.render_and_save("sales_report.html", context, "sales_report")
"""Генерация PDF-отчета по товарам из CSV-файла с помощью WeasyPrint.

Скрипт читает товары из data/products.csv, заполняет HTML-шаблон
templates/product_report.html (Jinja2) и сохраняет PDF-отчет
в output/product_report.pdf. После успешной генерации открывает
PDF в стандартной программе просмотра документов Windows.

Все пути определяются относительно расположения самого скрипта,
поэтому запуск возможен из любой текущей папки терминала.
"""

import csv
import io
import math
import os
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "products.csv"
TEMPLATE_DIR = BASE_DIR / "templates"
TEMPLATE_FILE = TEMPLATE_DIR / "product_report.html"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_PDF = OUTPUT_DIR / "product_report.pdf"

REQUIRED_COLUMNS = ("product", "price", "qty")


class DataError(Exception):
    """Ошибка данных CSV — выводится пользователю понятным сообщением."""


def fail(message: str) -> DataError:
    return DataError(message)


def format_money(value: float) -> str:
    """Форматирует сумму как '1 234,50' (пробел — разделитель тысяч)."""
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return text


def format_qty(value: float) -> str:
    """Целое количество печатается без дробной части, дробное — как есть."""
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def load_products(path: Path) -> list[tuple[str, float, float]]:
    """Читает CSV и возвращает список (название, цена, количество)."""
    if not path.is_file():
        raise fail(
            f"CSV-файл с товарами не найден: {path}\n"
            "Создайте файл data/products.csv по образцу из README.md."
        )

    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="cp1251")
        except UnicodeDecodeError:
            raise fail(
                f"Не удалось прочитать CSV-файл: {path}\n"
                "Сохраните файл в кодировке UTF-8 или Windows-1251."
            )

    reader = csv.DictReader(io.StringIO(text))

    fieldnames = [name.strip() for name in (reader.fieldnames or [])]
    reader.fieldnames = fieldnames
    if not fieldnames:
        raise fail(f"Заголовок CSV-файла пуст: {path}")

    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise fail(
            f"В CSV-файле отсутствуют обязательные колонки: {', '.join(missing)}.\n"
            f"Ожидается заголовок: {', '.join(REQUIRED_COLUMNS)}."
        )

    items: list[tuple[str, float, float]] = []
    for row_number, row in enumerate(reader, start=2):
        product = (row.get("product") or "").strip()
        price_raw = (row.get("price") or "").strip()
        qty_raw = (row.get("qty") or "").strip()

        # Полностью пустую строку пропускаем молча (лишние переводы строк).
        if not product and not price_raw and not qty_raw:
            continue

        if not product:
            raise fail(f"Строка {row_number}: не заполнено название товара (колонка 'product').")
        if not price_raw:
            raise fail(f"Строка {row_number}: не заполнена цена товара '{product}' (колонка 'price').")
        if not qty_raw:
            raise fail(f"Строка {row_number}: не заполнено количество товара '{product}' (колонка 'qty').")

        try:
            price = float(price_raw.replace(",", "."))
        except ValueError:
            raise fail(f"Строка {row_number}: цена '{price_raw}' — не число.")
        if not math.isfinite(price):
            raise fail(f"Строка {row_number}: цена '{price_raw}' в колонке 'price' — не корректное число (NaN или Infinity).")
        try:
            qty = float(qty_raw.replace(",", "."))
        except ValueError:
            raise fail(f"Строка {row_number}: количество '{qty_raw}' — не число.")
        if not math.isfinite(qty):
            raise fail(f"Строка {row_number}: количество '{qty_raw}' в колонке 'qty' — не корректное число (NaN или Infinity).")

        if price < 0:
            raise fail(f"Строка {row_number}: цена не может быть отрицательной ({price_raw}).")
        if qty <= 0:
            raise fail(f"Строка {row_number}: количество должно быть больше нуля ({qty_raw}).")

        items.append((product, price, qty))

    if not items:
        raise fail("CSV-файл не содержит ни одной строки с данными о товарах.")

    return items


def render_html(items: list[tuple[str, float, float]]) -> str:
    """Заполняет HTML-шаблон данными о товарах."""
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError:
        raise fail(
            "Не установлена библиотека Jinja2. Установите зависимости:\n"
            "pip install -r pdf_checkmaker/requirements.txt"
        )

    rows = [
        (product, format_money(price), format_qty(qty), format_money(price * qty))
        for product, price, qty in items
    ]
    total_sum = format_money(sum(price * qty for _, price, qty in items))

    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = environment.get_template(TEMPLATE_FILE.name)
    return template.render(
        items=rows,
        total_sum=total_sum,
        generated_date=date.today().strftime("%d.%m.%Y"),
    )


def generate_pdf(html: str) -> None:
    """Сохраняет HTML-отчет как PDF в папку output."""
    try:
        from weasyprint import HTML
    except ImportError:
        raise fail(
            "Не установлена библиотека WeasyPrint. Установите зависимости:\n"
            "pip install -r pdf_checkmaker/requirements.txt\n"
            "(для Windows также требуются GTK/Pango — см. README.md)."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf(OUTPUT_PDF)


def open_pdf(path: Path) -> None:
    """Открывает PDF стандартной программой просмотра документов Windows."""
    if not hasattr(os, "startfile"):
        return  # Не Windows — автоматическое открытие недоступно.
    try:
        os.startfile(path)  # noqa: S606 — намеренное открытие готового отчета
        print(f"PDF открыт в стандартной программе просмотра: {path}")
    except OSError as error:
        print(f"Не удалось открыть PDF автоматически: {error}")
        print(f"Откройте файл вручную: {path}")


def main() -> int:
    try:
        items = load_products(DATA_FILE)
        html = render_html(items)
        generate_pdf(html)
    except DataError as error:
        print(f"[ОШИБКА] {error}")
        return 1

    print(f"PDF-отчет успешно создан: {OUTPUT_PDF}")
    print(f"Товаров в отчете: {len(items)}")
    open_pdf(OUTPUT_PDF)
    return 0


if __name__ == "__main__":
    sys.exit(main())
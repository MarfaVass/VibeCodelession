"""Сценарий «Коммерческое предложение»: каталог CSV, выбор позиций, скидка, PDF.

Модуль не зависит от Tkinter — GUI только передает каталог, выбранные
позиции, скидку и реквизиты. Формулы:
    сумма позиции = цена × количество
    общая сумма до скидки = Σ сумма позиций
    скидка = общая сумма × % скидки / 100
    итоговая сумма = общая сумма − скидка

Деньги считаются в Decimal; промежуточные операции не округляются.
До копеек значения приводятся только при выводе (формате PDF), по
правилу «вверх» (0,005 → 0,01). Величина скидки округляется до копеек
перед вычитанием, поэтому строки с суммами всегда согласованы между
собой и не дают расхождений на копейки.

Товары с одинаковыми названиями, но разными SKU — разные товары.
Номер предложения при пустом поле генерируется автоматически (КП-...).
"""

import random
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from common import pdf_output
from common.csv_io import read_csv_rows
from common.errors import DataError
from common.numfmt import format_money
from common.validation import clean_text

REQUIRED_COLUMNS = ("sku", "name", "category", "price")
OPTIONAL_COLUMNS = ("description",)

MIN_DISCOUNT = Decimal("0")   # скидка только по явному действию пользователя
MAX_DISCOUNT = Decimal("90")

ALL_CATEGORIES = "Все категории"

# SKU демо-каталога для «Заполнить пример»; используются, только если
# эти товары реально есть в загруженном каталоге — несуществующие не придумываются.
DEMO_SKUS = ("IR-001", "IR-002")


def pick_demo_positions(catalogue: dict) -> list[dict]:
    """Позиции для кнопки «Заполнить пример» из реального каталога.

    Если в текущем каталоге есть демонстрационные SKU — берутся они
    (2 и 1 штука). Если их нет или каталог другой — первые два
    загруженных товара. Каталог не подменяется и не выдумывается.
    """
    by_sku = {item["sku"] for item in catalogue["items"]}
    skus = [sku for sku in DEMO_SKUS if sku in by_sku]
    if not skus:
        skus = [item["sku"] for item in catalogue["items"][:2]]
    qty_by_rank = (2, 1)
    return [
        {"sku": sku, "qty": qty_by_rank[min(rank, len(qty_by_rank) - 1)]}
        for rank, sku in enumerate(skus)
    ]


def quantize_money(value: Decimal) -> Decimal:
    """Приводит денежное значение к копейкам (правило «вверх»)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _format_discount(pct: Decimal) -> str:
    """Скидка для PDF: целая — '15', дробная — '12,5'."""
    if pct == pct.to_integral_value():
        return str(int(pct))
    return f"{pct}".replace(".", ",")


def generate_quotation_number() -> str:
    """Номер вида КП-ГГГГММДД-NNNN: сегодняшняя дата + случайный серийник."""
    return f"КП-{date.today():%Y%m%d}-{random.randint(0, 9999):04d}"


def validate_details(data: dict) -> dict:
    """Проверяет необязательные реквизиты предложения.

    Пустые поля возвращаются пустыми строками — шаблон не выводит
    соответствующие блоки, поэтому в документе нет пустых подписей.
    """
    return {
        "supplier": clean_text(data.get("supplier"), "поставщик", required=False),
        "recipient": clean_text(
            data.get("recipient"), "получатель предложения", required=False
        ),
        "number": clean_text(
            data.get("number"), "номер предложения", required=False
        ) or generate_quotation_number(),
        "valid_until": clean_text(
            data.get("valid_until"), "срок действия предложения", required=False
        ),
        "comment": clean_text(
            data.get("comment"), "комментарий", required=False, max_length=300
        ),
    }


def parse_discount(raw) -> Decimal:
    """Скидка в процентах: число от 0 до 90; пустое значение — 0.

    Принимает строку (пользовательский ввод) или Decimal (внутренние
    расчеты).
    """
    if isinstance(raw, Decimal):
        discount = raw
        text = f"{raw}"
    else:
        text = (raw or "").strip()
        if not text:
            return MIN_DISCOUNT
        try:
            discount = Decimal(text.replace(",", "."))
        except InvalidOperation:
            raise DataError(f"Скидка «{text}» — не число. Введите процент от 0 до 90.")
    if not discount.is_finite():
        raise DataError("Скидка — не корректное число. Введите процент от 0 до 90.")
    if discount < MIN_DISCOUNT:
        raise DataError("Скидка не может быть отрицательной.")
    if discount > MAX_DISCOUNT:
        raise DataError(f"Скидка не может быть больше {MAX_DISCOUNT} %.")
    return discount


def parse_quantity(raw) -> Decimal:
    """Количество позиции: целое, не меньше 1.

    Принимает строку (ввод пользователя) или число (Decimal/int —
    внутренние расчеты и тесты).
    """
    if isinstance(raw, Decimal):
        qty = raw
        text = f"{raw}"
    elif isinstance(raw, int):
        qty = Decimal(raw)
        text = f"{raw}"
    else:
        text = (raw or "").strip()
        try:
            qty = Decimal(text.replace(",", "."))
        except InvalidOperation:
            raise DataError(f"Количество «{text}» — не число.")
    if not qty.is_finite():
        raise DataError("Количество — не корректное число.")
    if qty != qty.to_integral_value():
        raise DataError(f"Количество должно быть целым числом (сейчас {text}).")
    if qty < 1:
        raise DataError("Количество должно быть не меньше 1.")
    return qty


def load_catalogue(path) -> dict:
    """Читает CSV-каталог товаров и проверяет строки.

    items — валидные товары; skipped — {"row", "reason"}; source_name.
    Повторный SKU с идентичными данными считается одной карточкой;
    повторный SKU с отличающимися данными (название, категория, цена,
    описание) — ошибка: предложение не создается, чтобы не предложить
    случайную версию товара.
    """
    fieldnames, raw_rows = read_csv_rows(path)

    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise DataError(
            "В CSV-файле отсутствуют обязательные колонки: "
            f"{', '.join(missing)}.\n"
            "Ожидается заголовок: sku,name,category,price[,description]"
        )

    items: list[dict] = []
    skipped: list[dict] = []
    seen: dict[str, dict] = {}
    for row_number, row in enumerate(raw_rows, start=2):
        sku = (row.get("sku") or "").strip()
        name = (row.get("name") or "").strip()
        category = (row.get("category") or "").strip()
        description = (row.get("description") or "").strip()
        price_raw = (row.get("price") or "").strip()

        if not sku and not name and not category and not price_raw:
            continue  # полностью пустая строка — не считается ошибкой

        reason = None
        price = None
        if not sku:
            reason = "не заполнен артикул (колонка 'sku')"
        elif not name:
            reason = "не заполнено название товара (колонка 'name')"
        elif not category:
            reason = "не указана категория (колонка 'category')"
        else:
            try:
                price = Decimal(price_raw.replace(",", "."))
            except InvalidOperation:
                reason = f"цена «{price_raw}» — не число"
            else:
                if not price.is_finite():
                    reason = f"цена «{price_raw}» — не корректное число (NaN или Infinity)"
                elif price <= 0:
                    reason = f"цена должна быть больше нуля (сейчас {price_raw})"

        if reason is not None:
            skipped.append({"row": row_number, "reason": reason})
            continue

        item = {"sku": sku, "name": name, "category": category,
                "price": price, "description": description}
        if sku in seen:
            previous = seen[sku]
            # Сравнение всех полей: только полностью одинаковый дубль склеивается.
            identical = (
                name == previous["name"]
                and category == previous["category"]
                and price == previous["price"]
                and description == previous["description"]
            )
            if not identical:
                raise DataError(
                    f"Строка {row_number}: артикул «{sku}» встречается повторно "
                    "с другими данными (название, категория, цена или "
                    "описание различаются).\n"
                    "Устраните дубли в каталоге — предложение не создается, "
                    "чтобы не предложить случайно выбранную версию товара."
                )
            skipped.append({
                "row": row_number,
                "reason": "повторная строка с уже загруженным артикулом",
            })
            continue

        seen[sku] = item
        items.append(item)

    if not items:
        raise DataError(
            "CSV-файл не содержит ни одной корректно заполненной "
            "строки каталога."
        )

    return {"items": items, "skipped": skipped, "source_name": Path(path).name}


def get_categories(catalogue: dict) -> list[str]:
    """Категории определяются из данных каталога, а не из кода."""
    return sorted({item["category"] for item in catalogue["items"]})


def filter_items(catalogue: dict, category: str | None = None,
                 search: str = "") -> list[dict]:
    """Фильтр каталога: категория + поиск по артикулу и названию.

    Поиск нечувствителен к регистру; категория «Все категории» ничего не
    исключает.
    """
    query = (search or "").strip().casefold()
    result = []
    for item in catalogue["items"]:
        if category and category != ALL_CATEGORIES and item["category"] != category:
            continue
        if query and (query not in item["sku"].casefold()
                      and query not in item["name"].casefold()):
            continue
        result.append(item)
    return result


def normalize_positions(positions: list[dict]) -> dict[str, Decimal]:
    """Позиции предложения: sku → количество (целое ≥ 1).

    Повторяющаяся позиция складывается с уже выбранной; нулевые и
    отрицательные количества отклоняются.
    """
    merged: dict[str, Decimal] = {}
    for position in positions:
        if not isinstance(position, dict):
            raise DataError("Позиция предложения задана некорректным типом данных.")
        sku = (position.get("sku") or "").strip()
        if not sku:
            raise DataError("В составе предложения есть позиция без артикула.")
        qty = parse_quantity(position.get("qty"))
        merged[sku] = merged.get(sku, Decimal("0")) + qty
    return merged


def calculate_quotation(catalogue: dict, positions: list[dict],
                        discount_raw: str | Decimal = "0") -> dict:
    """Рассчитывает суммы предложения (формулы в докстринге модуля)."""
    merged = normalize_positions(positions)
    if not merged:
        raise DataError(
            "Не выбран ни один товар.\n"
            "Добавьте в предложение позиции из каталога."
        )

    by_sku = {item["sku"]: item for item in catalogue["items"]}
    unknown = [sku for sku in merged if sku not in by_sku]
    if unknown:
        raise DataError(
            "В предложении есть товар, отсутствующий в каталоге: "
            f"{', '.join(unknown)}."
        )

    rows: list[dict] = []
    line_sums: list[Decimal] = []
    for sku, qty in merged.items():
        item = by_sku[sku]
        line_sum = quantize_money(item["price"] * qty)
        line_sums.append(line_sum)
        rows.append({
            "sku": item["sku"], "name": item["name"],
            "category": item["category"], "description": item["description"],
            "qty": qty, "price": item["price"], "line_sum": line_sum,
        })

    subtotal = sum(line_sums, Decimal("0"))
    if subtotal < 0:
        raise DataError("Итоговая сумма не может быть отрицательной.")
    # Одна проверка скидки здесь: parse_discount принимает и строку ввода,
    # и Decimal внутренних расчетов.
    discount_pct = parse_discount(discount_raw)
    discount_amount = quantize_money(subtotal * discount_pct / 100)
    grand_total = subtotal - discount_amount

    return {
        "rows": rows,
        "subtotal": subtotal,
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "grand_total": grand_total,
    }


def build_context(catalogue: dict, positions: list[dict],
                  discount_raw: str | Decimal = "0",
                  details: dict | None = None) -> dict:
    """Готовит контекст для HTML-шаблона коммерческого предложения."""
    calc = calculate_quotation(catalogue, positions, discount_raw)
    details = validate_details(details or {})
    has_discount = calc["discount_pct"] > 0

    context = {
        "generated_date": date.today().strftime("%d.%m.%Y"),
        # Реквизиты: шаблон показывает блок только если что-то заполнено.
        "supplier": details["supplier"],
        "recipient": details["recipient"],
        "number": details["number"],
        "valid_until": details["valid_until"],
        "comment": details["comment"],
        # Позиции: цены и суммы уже приведены к копейкам.
        "items": [
            {
                "sku": row["sku"],
                "name": row["name"],
                # Описание показывается только то, что есть в каталоге:
                # характеристики не придумываются.
                "description": row["description"],
                "qty": int(row["qty"]),
                "price": format_money(quantize_money(row["price"])),
                "line_sum": format_money(row["line_sum"]),
            }
            for row in calc["rows"]
        ],
        "subtotal": format_money(calc["subtotal"]),
        # Скидка выводится только если пользователь явно задал ее больше нуля.
        "has_discount": has_discount,
        "discount_pct": _format_discount(calc["discount_pct"]),
        "discount_amount": format_money(calc["discount_amount"]),
        "grand_total": format_money(calc["grand_total"]),
    }
    return context


def create_quotation_pdf(catalogue: dict, positions: list[dict],
                         discount_raw: str | Decimal = "0",
                         details: dict | None = None) -> Path:
    """Создает PDF коммерческого предложения и возвращает путь к файлу."""
    context = build_context(catalogue, positions, discount_raw, details)
    return pdf_output.render_and_save("quotation.html", context, "quotation")
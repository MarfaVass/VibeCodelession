# -*- coding: utf-8 -*-
"""Валидация значений для веб-интерфейса.

Streamlit сам не даёт ввести отрицательное число (number_input с
min_value), поэтому здесь сосредоточены чистые функции-парсеры:
ими пользуются и интерфейс, и smoke-тест. Дубликаты статей
проверяются в categories.add_category.
"""

import math
from typing import Optional


def parse_amount(raw) -> Optional[float]:
    """Разобрать значение суммы по правилам отчёта.

    Правила: число строго больше нуля (неотрицательное в смысле ввода,
    но ноль — это «поле пустое» и не сохраняется), разделитель — точка
    или запятая (99,50 -> 99.50), дробная часть — до двух знаков.

    :param raw: сырые данные от пользователя.
    :return: сумма как float, либо None, если поле пустое/некорректное.
    """
    if raw is None:
        return None
    cleaned = str(raw).strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(amount) or amount <= 0:
        return None
    return round(amount, 2)


def clean_text(raw) -> str:
    """Обрезать внешние пробелы; пустая строка означает «поле не заполнено».

    :param raw: сырые данные от пользователя.
    :return: строка без внешних пробелов.
    """
    return str(raw or "").strip()

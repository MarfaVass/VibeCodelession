"""Валидация полей форм PDF Studio.

Модуль не зависит от Tkinter и используется как из GUI, так и из тестов:
все функции принимают сырые значения (строки) и либо возвращают чистое
значение, либо возбуждают DataError с понятным сообщением на русском языке.
"""

from datetime import date

from common.errors import DataError

MAX_TEXT_LENGTH = 120


def clean_text(value: str, field_label: str, *, required: bool = True,
               max_length: int = MAX_TEXT_LENGTH) -> str:
    """Убирает лишние пробелы; при required=True пустое значение — ошибка."""
    text = (value or "").strip()
    if not text:
        if required:
            raise DataError(f"Не заполнено поле «{field_label}».")
        return ""
    if len(text) > max_length:
        raise DataError(
            f"Поле «{field_label}» слишком длинное "
            f"(максимум {max_length} символов)."
        )
    return text


def parse_date_ru(value: str, field_label: str, *,
                  default_today: bool = True) -> date:
    """Разбирает дату в формате ДД.ММ.ГГГГ.

    Пустое значение заменяется сегодняшней датой, если default_today=True.
    """
    text = (value or "").strip()
    if not text:
        if default_today:
            return date.today()
        raise DataError(f"Не заполнено поле «{field_label}».")
    try:
        parsed = date(*map(int, text.split(".")[::-1]))
    except (ValueError, TypeError):
        raise DataError(
            f"Поле «{field_label}»: «{text}» — не корректная дата. "
            "Введите дату в формате ДД.ММ.ГГГГ, "
            f"например {date.today().strftime('%d.%m.%Y')}."
        )
    return parsed
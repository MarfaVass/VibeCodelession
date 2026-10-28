"""Форматирование чисел для PDF-документов PDF Studio.

Функции перенесены без изменений из работающего pdf_checkmaker/pdf_generator.py,
чтобы все документы студии выглядели одинаково.
"""


def format_money(value: float) -> str:
    """Форматирует сумму как '1 234,50' (пробел — разделитель тысяч)."""
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return text


def format_qty(value: float) -> str:
    """Целое количество печатается без дробной части, дробное — как есть."""
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def format_percent(value: float) -> str:
    """Процент с одним знаком после запятой: '12,4'."""
    return f"{value:.1f}".replace(".", ",")
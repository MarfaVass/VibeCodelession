"""Чтение CSV-файлов с определением кодировки.

Поддерживаются UTF-8 (в том числе с BOM, utf-8-sig) и Windows-1251 —
тот же порядок, что отработан в pdf_checkmaker/pdf_generator.py.
"""

import csv
import io
from pathlib import Path
from typing import List, Tuple

from common.errors import DataError


def read_csv_rows(path) -> Tuple[List[str], List[dict]]:
    """Читает CSV и возвращает (список колонок, список строк-словарей).

    Значения полей не обрезаются здесь — обрезка происходит в валидаторах
    конкретных сценариев, где известны правила каждого поля.
    """
    csv_path = Path(path)
    if not csv_path.is_file():
        raise DataError(f"CSV-файл не найден: {csv_path}")

    try:
        text = csv_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = csv_path.read_text(encoding="cp1251")
        except UnicodeDecodeError:
            raise DataError(
                f"Не удалось прочитать CSV-файл: {csv_path}\n"
                "Сохраните файл в кодировке UTF-8 или Windows-1251."
            )

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [name.strip() for name in (reader.fieldnames or [])]
    reader.fieldnames = fieldnames
    if not fieldnames:
        raise DataError(f"Заголовок CSV-файла пуст: {csv_path}")

    rows = [dict(row) for row in reader]
    return fieldnames, rows
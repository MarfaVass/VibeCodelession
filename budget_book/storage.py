# -*- coding: utf-8 -*-
"""Загрузка и сохранение бюджета в JSON-файле.

Единственный файл данных — data/budget.json (относительно корня проекта).
При отсутствии файл создаётся автоматически. При повреждении старый файл
переносится в data/budget.corrupt.json, и приложение начинает с чистого
бюджета — так испорченные данные можно всегда посмотреть вручную.
"""

import json
import sys
from pathlib import Path

import models

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_FILE = DATA_DIR / "budget.json"
CORRUPT_FILE = DATA_DIR / "budget.corrupt.json"

_CORRUPT_NOTICE = (
    "Файл данных data/budget.json повреждён или имеет неожиданную структуру.\n"
    "Испорченная копия сохранена в data/budget.corrupt.json,\n"
    "приложение начинает работу с новым пустым бюджетом."
)


def load_budget() -> dict:
    """Загрузить бюджет из JSON-файла.

    Если файла нет — создаётся новый пустой бюджет и сразу сохраняется.
    Если файл повреждён (не читается или не похож на бюджет) — испорченный
    файл переносится в data/budget.corrupt.json и создаётся новый бюджет.

    :return: структура бюджета (см. models.new_budget).
    """
    if not DATA_FILE.exists():
        budget = models.new_budget()
        save_budget(budget)
        return budget

    raw = DATA_FILE.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None

    if not models.is_valid_budget(data):
        # errors="replace" и try/except — не падаем и на неудачном переносе
        try:
            CORRUPT_FILE.write_text(raw, encoding="utf-8")
        except OSError:
            pass
        print(_CORRUPT_NOTICE, file=sys.stderr)
        budget = models.new_budget()
        save_budget(budget)
        return budget

    data.setdefault(models.KEY_PLANNED_INCOME, [])
    data.setdefault(models.KEY_ACTUAL_INCOME, [])
    data.setdefault(models.KEY_ACTUAL_EXPENSES, [])
    data.setdefault(models.KEY_PLANNED_EXPENSES, {})
    for kind in models.EXPENSE_KINDS:
        data[models.KEY_PLANNED_EXPENSES].setdefault(kind, [])
    return data


def save_budget(data: dict) -> None:
    """Сохранить бюджет в JSON-файл (создавая каталог data/, если нужно).

    :param data: структура бюджета.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

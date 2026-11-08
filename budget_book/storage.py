# -*- coding: utf-8 -*-
"""Загрузка и сохранение бюджета в JSON-файле.

Единственный файл данных — data/budget.json (относительно корня проекта).
При первом запуске создаётся автоматически. Формат — по месяцам
(см. models): {«months»: {«YYYY-MM»: блок}}. Если файл повреждён или
имеет неожиданную структуру, испорченная копия переносится в
data/budget.corrupt.json и приложение начинает с чистого бюджета.
Старый CLI-формат (план/факт в корне файла) автоматически мигрируется
в текущий месяц — данные не теряются.
"""

import json
import sys
from datetime import date
from pathlib import Path

import categories
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


def _today_month_key() -> str:
    """Ключ текущего календарного месяца «YYYY-MM».

    :return: строка-ключ.
    """
    today = date.today()
    return models.month_key(today.year, today.month)


def _needs_flat_migration(data: dict) -> bool:
    """Есть ли в месяцах записи без ключа «group» (плоские форматы)?

    :param data: структура бюджета.
    :return: True, если миграция записи требуется.
    """
    for block in data[models.KEY_MONTHS].values():
        for collection in (models.KEY_PLANNED_ARTICLES, models.KEY_ACTUAL_EXPENSES):
            for entry in block.get(collection, []):
                if isinstance(entry, dict) and models.KEY_GROUP not in entry:
                    return True
    return False


def _migrate_flat_month_entries(data: dict) -> None:
    """Прогнать месяцы через миграцию плоских категорий (v2 → v3).

    Записи без «group» переезжают в «Прочее» как подкатегории; их имена
    дописываются в справочник, чтобы записи остались выбираемыми.

    :param data: структура бюджета (изменяется на месте).
    """
    if not _needs_flat_migration(data):
        return
    catalog = categories.load_categories()
    for key in models.month_keys(data):
        moved = models.migrate_flat_entries(models.ensure_month(data, key))
        for name in moved:
            if name == models.KEY_UNKNOWN_GROUP:
                continue
            categories.add_subcategory(catalog, models.KEY_UNKNOWN_GROUP, name,
                                       path=None)
    categories.save_categories(catalog)
    save_budget(data)


def _migrate_legacy_top_level(data: dict) -> dict:
    """Миграция CLI-формата (план/факт в корне) → формат по месяцам.

    :param data: словарь CLI-формата.
    :return: структура бюджета нового формата.
    """
    budget = models.migrate_legacy_budget(data)
    print("Данные старого CLI-формата перенесены в текущий месяц "
          "(плоские категории — в группу «Прочее»).", file=sys.stderr)
    return budget


def load_budget() -> dict:
    """Загрузить бюджет, приводя всё к формату по месяцам с группами.

    Нет файла или файл повреждён — создаётся новый пустой бюджет
    (испорченный переносится в data/budget.corrupt.json). Данные
    CLI-версии (план/факт в корне) автоматически переносятся в текущий
    месяц, записи с плоскими категориями — в группу «Прочее».

    :return: структура бюджета {months: {«YYYY-MM»: блок}}.
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

    if not isinstance(data, dict):
        print(_CORRUPT_NOTICE, file=sys.stderr)
        try:
            CORRUPT_FILE.write_text(raw, encoding="utf-8")
        except OSError:
            pass
        budget = models.new_budget()
        save_budget(budget)
        return budget

    if models.is_valid_budget(data):
        for key in list(data[models.KEY_MONTHS]):
            models.ensure_month(data, key)
        _migrate_flat_month_entries(data)
        return data

    if data:  # словарь без «months» — данные CLI-версии
        budget = _migrate_legacy_top_level(data)
        save_budget(budget)
        return budget

    print(_CORRUPT_NOTICE, file=sys.stderr)
    try:
        CORRUPT_FILE.write_text(raw, encoding="utf-8")
    except OSError:
        pass
    budget = models.new_budget()
    save_budget(budget)
    return budget


def save_budget(data: dict) -> None:
    """Сохранить бюджет в JSON-файл (создавая каталог data/, если нужно).

    :param data: структура бюджета.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

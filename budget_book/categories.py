# -*- coding: utf-8 -*-
"""Справочник расходных категорий: data/categories.json.

Файл создаётся автоматически из дефолтного списка при первом запуске.
Категория теперь всегда выбирается из списка — свободный текст отключён,
поэтому и отчёт, и диаграммы остаются согласованными между собой
(порядок строк/секторов и фиксированный цвет категории).
"""

import json
import sys
from pathlib import Path
from typing import List, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
CATEGORIES_FILE = DATA_DIR / "categories.json"

DEFAULT_CATEGORIES: List[str] = [
    "Жильё",
    "Продукты",
    "Транспорт",
    "Здоровье",
    "Образование",
    "Развлечения",
    "Одежда",
    "Связь и интернет",
    "Подписки",
    "Подарки",
    "Прочее",
]

_CORRUPT_NOTICE = (
    "Файл data/categories.json повреждён или не является списком."
    " Испорченная копия сохранена в data/categories.corrupt.json,"
    " справочник восстановлен из дефолтного списка."
)


def is_valid_catalog(data) -> bool:
    """Проверить, что JSON — список непустых строк-категорий.

    :param data: объект, полученный из json.load.
    :return: True, если это пригодный справочник.
    """
    return (
        isinstance(data, list)
        and bool(data)
        and all(isinstance(name, str) and name.strip() for name in data)
    )


def load_categories(path: Path = CATEGORIES_FILE) -> List[str]:
    """Загрузить справочник, при необходимости создав или восстановив его.

    Нет файла — записывается дефолтный список. Повреждён файл — его копия
    переносится в categories.corrupt.json рядом с оригиналом, справочник
    восстанавливается из дефолта, пользователь получает сообщение.

    :param path: файл справочника (переопределяется в тестах).
    :return: список категорий.
    """
    if not path.exists():
        catalog = list(DEFAULT_CATEGORIES)
        save_categories(catalog, path)
        return catalog

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        data = None

    if not is_valid_catalog(data):
        corrupt_path = path.with_name(path.stem + ".corrupt.json")
        try:
            corrupt_path.write_text(path.read_text(encoding="utf-8", errors="replace"),
                                    encoding="utf-8")
        except OSError:
            pass
        print(_CORRUPT_NOTICE, file=sys.stderr)
        catalog = list(DEFAULT_CATEGORIES)
        save_categories(catalog, path)
        return catalog

    return list(data)


def save_categories(catalog: List[str], path: Path = CATEGORIES_FILE) -> None:
    """Сохранить справочник (каталог data/ создаётся при необходимости).

    :param catalog: список категорий.
    :param path: файл справочника.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_category(name: str) -> str:
    """Обрезать пробелы и свести регистр — для проверки дубликатов.

    :param name: введённое название категории.
    :return: нормализованная строка.
    """
    return name.strip().casefold()


def add_category(catalog: List[str], name: str, path: Path = CATEGORIES_FILE) -> bool:
    """Добавить категорию, если её ещё нет (регистр и пробелы игнорируются).

    :param catalog: текущий справочник (изменяется на месте).
    :param name: новое название.
    :param path: файл справочника для немедленного сохранения.
    :return: True — добавлено; False — дубликат.
    """
    normalized = normalize_category(name)
    if any(normalize_category(existing) == normalized for existing in catalog):
        return False
    cleaned = name.strip()
    catalog.append(cleaned)
    save_categories(catalog, path)
    return True


def select_category_by_number(catalog: List[str], raw: str) -> Optional[str]:
    """Выбрать категорию по номеру из справочника (чистая функция).

    Номер — строка от 1 до длины списка. Всё остальное (не число,
    ноль, выход за границы, пустая строка) даёт None.

    :param catalog: список категорий.
    :param raw: ответ пользователя.
    :return: название категории или None.
    """
    raw = (raw or "").strip()
    if not raw.isdigit():
        return None
    index = int(raw)
    if not 1 <= index <= len(catalog):
        return None
    return catalog[index - 1]


def choose_category(catalog: List[str]) -> str:
    """Спросить категорию выбором по номеру из напечатанного списка.

    При неверном номере печатает подсказку и повторяет запрос.

    :param catalog: список категорий.
    :return: выбранная категория.
    """
    print("Выберите категорию:")
    for number, name in enumerate(catalog, start=1):
        print(f"  {number:>2}. {name}")
    hint = f"номер от 1 до {len(catalog)}"
    while True:
        raw = input(f"Номер категории ({hint}): ")
        category = select_category_by_number(catalog, raw)
        if category is not None:
            return category
        print(f"Ошибка: нужен номер из списка ({hint}).", file=sys.stderr)


def print_catalog(catalog: Union[List[str], None] = None) -> None:
    """Напечатать справочник с номерами.

    :param catalog: список категорий; None — загрузить/создать файл.
    """
    names = load_categories() if catalog is None else catalog
    print("Справочник расходных категорий:")
    for number, name in enumerate(names, start=1):
        print(f"  {number:>2}. {name}")

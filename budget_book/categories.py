# -*- coding: utf-8 -*-
"""Справочник статей расходов: data/categories.json — два уровня.

Формат: словарь «группа → список подкатегорий»:
    {"Жильё": ["Аренда", "Коммунальные услуги", ...], "Здоровье": [...], ...}

Файл создаётся автоматически из дефолтного списка при первом запуске.
Статья (группа и подкатегория) всегда выбирается из списка — свободный
текст отключён, поэтому порядок строк отчёта, цветов и секторов
согласован. Плоский старый формат (список строк) автоматически
преобразуется: знакомые имена становятся группами с их дефолтными
подкатегориями, незнакомые отбрасываются (см. REPORT.md).
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
CATEGORIES_FILE = DATA_DIR / "categories.json"

# Дефолтный двухуровневый справочник (порядок задаёт цвета на диаграммах)
DEFAULT_CATEGORIES: Dict[str, List[str]] = {
    "Жильё": ["Аренда", "Коммунальные услуги", "Ремонт", "Работники", "Участок"],
    "Здоровье": ["Аптека", "Врачи", "Анализы", "Страховка"],
    "Одежда": ["Верхняя одежда", "Обувь", "Аксессуары"],
    "Развлечения": ["Кино", "Кафе", "Хобби", "Подписки"],
    "Обучение": ["Курсы", "Книги", "Репетиторы"],
    "Связь": ["Мобильная связь", "Интернет"],
    "Транспорт": ["Общественный", "Такси", "Топливо", "Ремонт авто"],
    "Путешествия": ["Билеты", "Отели", "Экскурсии"],
    "Прочее": ["Подарки", "Непредвиденное"],
}

_CORRUPT_NOTICE = (
    "Файл data/categories.json повреждён или не является справочником."
    " Испорченная копия сохранена рядом (categories.corrupt.json),"
    " справочник восстановлен из дефолта."
)

ADDED = "added"          # добавлено
REMOVED = "removed"      # удалено
DUPLICATE = "duplicate"
NO_GROUP = "no_group"


def is_valid_catalog(data) -> bool:
    """Проверить JSON: словарь «строка → список непустых строк».

    Пустые группы допустимы; подкатегории-непустые строки — тоже.

    :param data: объект, полученный из json.load.
    :return: True, если это пригодный двухуровневый справочник.
    """
    if not isinstance(data, dict):
        return False
    for group, subs in data.items():
        if not isinstance(group, str) or not group.strip():
            return False
        if not isinstance(subs, list):
            return False
        if any(not isinstance(sub, str) or not sub.strip() for sub in subs):
            return False
    return bool(data)


def normalize_entity(name) -> str:
    """Обрезать пробелы и свести регистр — для проверки дубликатов.

    :param name: введённое название группы или подкатегории.
    :return: нормализованная строка.
    """
    return str(name or "").strip().casefold()


def _migrate_flat_catalog(data: list) -> Dict[str, List[str]]:
    """Перенести плоский справочник CLI/Streamlit-v2 в двухуровневый.

    Результат — дефолтная структура целиком: старые имена, совпадающие
    с дефолтными группами (Жильё, Транспорт и т. д.), продолжают жить
    как группы с дефолтными подкатегориями; остальные старые имена
    (Продукты, Подписки и т. п.) отбрасываются — записям бюджета с ними
    при загрузке всё равно назначается «Прочее» (см. storage), так что
    ничего не теряется в отчёте.

    :param data: старый список категорий-строк (используется для лога).
    :return: дефолтный двухуровневый справочник.
    """
    return {group: list(subs) for group, subs in DEFAULT_CATEGORIES.items()}


def load_categories(path: Path = CATEGORIES_FILE) -> Dict[str, List[str]]:
    """Загрузить справочник, при необходимости создав или восстановив его.

    Нет файла — пишется дефолтный список. Повреждён (или это старый
    плоский список) — мигрируется/восстанавливается, о копии сообщается.

    :param path: файл справочника (переопределяется в тестах).
    :return: словарь «группа → [подкатегории]».
    """
    if not path.exists():
        catalog = {group: list(subs) for group, subs in DEFAULT_CATEGORIES.items()}
        save_categories(catalog, path)
        return catalog

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        data = None

    if isinstance(data, list):  # плоский справочник прошлой версии
        catalog = _migrate_flat_catalog(data)
        corrupt_path = path.with_name(path.stem + ".corrupt.json")
        try:
            corrupt_path.write_text(path.read_text(encoding="utf-8", errors="replace"),
                                    encoding="utf-8")
        except OSError:
            pass
        print("data/categories.json старого плоского формата; мигрирован в "
              "двухуровневый. Старый файл сохранён как categories.corrupt.json.",
              file=sys.stderr)
        save_categories(catalog, path)
        return catalog

    if not is_valid_catalog(data):
        corrupt_path = path.with_name(path.stem + ".corrupt.json")
        try:
            corrupt_path.write_text(path.read_text(encoding="utf-8", errors="replace"),
                                    encoding="utf-8")
        except OSError:
            pass
        print(_CORRUPT_NOTICE, file=sys.stderr)
        catalog = {group: list(subs) for group, subs in DEFAULT_CATEGORIES.items()}
        save_categories(catalog, path)
        return catalog

    return {group: list(subs) for group, subs in data.items()}


def save_categories(catalog: Dict[str, List[str]], path: Path = CATEGORIES_FILE) -> None:
    """Сохранить справочник (каталог data/ создаётся при необходимости).

    :param catalog: двухуровневый справочник.
    :param path: файл справочника.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_group(catalog: Dict[str, List[str]], group: str) -> bool:
    """Есть ли группа (без дедупликации)? — вспомогательная проверка."""
    return any(normalize_entity(existing) == normalize_entity(group) for existing in catalog)


def group_key(catalog: Dict[str, List[str]], group: str) -> Optional[str]:
    """Актуальное имя группы по нормализованному вводу.

    :param catalog: справочник.
    :param group: ввод пользователя.
    :return: имя группы в справочнике или None.
    """
    normalized = normalize_entity(group)
    for existing in catalog:
        if normalize_entity(existing) == normalized:
            return existing
    return None


def add_group(catalog: Dict[str, List[str]], name: str,
              subcategories: Union[List[str], None] = None,
              path: Path = CATEGORIES_FILE) -> str:
    """Добавить в справочник группу (опционально сразу с подкатегориями).

    Подкатегории добавляются по порядку (дубликаты внутри них,
    в группе и во всём справочнике, отбрасываются молча — пользователь
    в UI видит только финальный состав группы).

    :param catalog: справочник (изменяется на месте).
    :param name: название группы.
    :param subcategories: подкатегории или None (пустая группа).
    :param path: файл справочника; None — не сохранять (массовая миграция).
    :return: ADDED | DUPLICATE («группа уже есть»).
    """
    existing = group_key(catalog, name)
    if existing is not None:
        return DUPLICATE

    cleaned_name = str(name).strip()
    subs: List[str] = []
    seen = set()
    for sub in subcategories or []:
        normalized = normalize_entity(sub)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        subs.append(str(sub).strip())
    catalog[cleaned_name] = subs
    if path is not None:
        save_categories(catalog, path)
    return ADDED


def add_subcategory(catalog: Dict[str, List[str]], group: str, name: str,
                    path: Path = CATEGORIES_FILE) -> str:
    """Добавить подкатегорию в существующую группу.

    :param catalog: справочник (изменяется на месте).
    :param group: существующая группа.
    :param name: название подкатегории.
    :param path: файл справочника; None — не сохранять (массовая миграция).
    :return: ADDED | DUPLICATE | NO_GROUP (группы нет).
    """
    existing = group_key(catalog, group)
    if existing is None:
        return NO_GROUP
    normalized = normalize_entity(name)
    if not normalized:
        return DUPLICATE  # пустое имя трактуем как «нечего добавлять»
    if any(normalize_entity(sub) == normalized for sub in catalog[existing]):
        return DUPLICATE
    catalog[existing].append(str(name).strip())
    if path is not None:
        save_categories(catalog, path)
    return ADDED


def remove_group(catalog: Dict[str, List[str]], group: str,
                 path: Path = CATEGORIES_FILE) -> str:
    """Удалить группу целиком (с её подкатегориями).

    :param catalog: справочник (изменяется на месте).
    :param group: удаляемая группа.
    :param path: файл справочника.
    :return: REMOVED (успешно удалено) | NO_GROUP.
    """
    existing = group_key(catalog, group)
    if existing is None:
        return NO_GROUP
    catalog.pop(existing)
    save_categories(catalog, path)
    return REMOVED


def remove_subcategory(catalog: Dict[str, List[str]], group: str, name: str,
                       path: Path = CATEGORIES_FILE) -> str:
    """Удалить подкатегорию из группы.

    :param catalog: справочник (изменяется на месте).
    :param group: группа.
    :param name: подкатегория.
    :param path: файл справочника.
    :return: REMOVED (удалено) | NO_GROUP (нет группы или подкатегории).
    """
    existing = group_key(catalog, group)
    if existing is None:
        return NO_GROUP
    normalized = normalize_entity(name)
    for index, sub in enumerate(catalog[existing]):
        if normalize_entity(sub) == normalized:
            catalog[existing].pop(index)
            save_categories(catalog, path)
            return REMOVED
    return NO_GROUP


def group_color_index(catalog: Dict[str, List[str]], group: str) -> int:
    """Индекс группы в справочнике — для фиксированного цвета диаграмм.

    :param catalog: справочник.
    :param group: название группы.
    :return: индекс или -1 (группы нет).
    """
    for index, existing in enumerate(catalog):
        if existing == group:
            return index
    return -1


def group_names(catalog: Dict[str, List[str]]) -> List[str]:
    """Имена групп в порядке справочника.

    :param catalog: справочник.
    """
    return list(catalog)

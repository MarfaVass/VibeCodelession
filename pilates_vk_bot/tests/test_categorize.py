"""Тесты справочника направлений (категорий).

После переработки логики категория определяется только кнопкой главного
меню, поэтому автоматическая классификация удалена. Здесь проверяется
единый справочник подписей, который используют клавиатуры, интро и заявки.
"""

from __future__ import annotations

import json

from bot import keyboards
from bot.categorize import CATEGORY_LABELS, VALID_CATEGORIES


def test_four_directions_defined() -> None:
    assert set(VALID_CATEGORIES) == {"specialist", "club", "international", "client"}
    assert len(CATEGORY_LABELS) == 4


def test_labels_are_concrete_and_understandable() -> None:
    """Подписи направлений конкретные и совпадают с кнопками главного меню."""

    for category, label in CATEGORY_LABELS.items():
        assert label in _main_menu_label(category)
        assert len(label) <= 40, (category, label)


def _main_menu_label(category: str) -> str:
    actions = [
        b["action"] for row in json.loads(keyboards.main_keyboard())["buttons"]
        for b in row
    ]
    for action in actions:
        if action["payload"].get("category") == category:
            return action["label"]
    raise AssertionError(f"кнопка категории {category} не найдена в главном меню")


def test_button_payloads_match_the_four_directions() -> None:
    """Главное меню содержит ровно четыре кнопки направлений и «Помощь»."""

    kb = json.loads(keyboards.main_keyboard())
    actions = [b["action"] for row in kb["buttons"] for b in row]
    category_payloads = [a["payload"]["category"] for a in actions if "category" in a.get("payload", {})]
    assert set(category_payloads) == set(VALID_CATEGORIES)
    assert any(a["payload"].get("cmd") == "/help" for a in actions)


def test_branch_keyboard_returns_to_menu_with_clear_label() -> None:
    """Кнопка ветки возвращает в главное меню с конкретной подписью."""

    kb = json.loads(keyboards.category_keyboard("client"))
    actions = [b["action"] for row in kb["buttons"] for b in row]
    menu_buttons = [a for a in actions if a["payload"].get("cmd") == "/menu"]
    assert len(menu_buttons) == 1
    assert menu_buttons[0]["label"] == "Выбрать другое направление"
    # кнопка заявки тоже есть и запускает /book
    assert any(a["payload"].get("cmd") == "/book" for a in actions)


def test_vk_limit_all_labels_40_chars() -> None:
    """VK отклоняет кнопки с подписью длиннее 40 символов (VKAPIError 911).

    Проверяются ВСЕ клавиатуры проекта: главное меню, клавиатуры веток для
    каждой категории и клавиатура подтверждения заявки.
    """

    kb_strings = {
        "main": keyboards.main_keyboard(),
        **{f"category:{cat}": keyboards.category_keyboard(cat)
           for cat in VALID_CATEGORIES},
        "confirm": keyboards.confirm_keyboard(),
        "empty": keyboards.empty_keyboard(),
    }
    for name, kb_str in kb_strings.items():
        buttons = [b["action"] for row in json.loads(kb_str)["buttons"] for b in row]
        for action in buttons:
            label = action["label"]
            assert 1 <= len(label) <= 40, (name, repr(label), len(label))


def test_inline_keyboard_has_no_one_time() -> None:
    """VK отклоняет inline-клавиатуры с one_time (VKAPIError 911):

    «one_time field is not available for inline keyboard».
    Проверяются все клавиатуры проекта; у inline-клавиатур флаг one_time
    должен быть false, у обычных — любое допустимое значение.
    """

    kb_strings = {
        "main": keyboards.main_keyboard(),
        **{f"category:{cat}": keyboards.category_keyboard(cat)
           for cat in VALID_CATEGORIES},
        "confirm": keyboards.confirm_keyboard(),
        "empty": keyboards.empty_keyboard(),
    }
    for name, kb_str in kb_strings.items():
        data = json.loads(kb_str)
        if data["inline"]:
            assert data["one_time"] is False, (
                f"{name}: inline-клавиатура не должна быть one_time "
                f"(VKAPIError_911)"
            )
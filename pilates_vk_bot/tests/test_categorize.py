"""Тесты определения категории клиента."""

from __future__ import annotations

import pytest

from bot.categorize import (
    CategoryDecision,
    CategoryStatus,
    classify_by_keywords,
    normalize_menu_number,
)

CLEAR_CASES = [
    # (сообщение, ожидаемая категория)
    ("Хочу стать тренером по пилатесу, пройти обучение и сертификацию", "specialist"),
    ("Я инструктор, интересует курс Matwork 1 и повышение квалификации", "specialist"),
    ("Мы фитнес-клуб, хотим обучить сотрудников семинаром на территории", "club"),
    ("Представляю студию, интересует корпоративное обучение тренеров", "club"),
    ("We are an international academy and want to invite Andrey to a conference", "international"),
    ("Организация из Европы хочет семинар за рубежом", "international"),
    ("Хочу записаться на персональные тренировки, пробное занятие", "client"),
    ("Болит спина, интересуюсь занятием для себя, начать заниматься", "client"),
]

AMBIGUOUS_CASES = [
    "Привет",
    "Здравствуйте",
    "Какая у вас методика?",
]


@pytest.mark.parametrize(("text", "expected"), CLEAR_CASES)
def test_clear_categories_by_keywords(text: str, expected: str) -> None:
    decision = classify_by_keywords(text)
    assert decision.is_confident
    assert decision.category == expected


@pytest.mark.parametrize("text", AMBIGUOUS_CASES)
def test_ambiguous_queries_are_not_forced(text: str) -> None:
    decision = classify_by_keywords(text)
    assert not decision.is_confident
    assert decision.category is None
    assert decision.status == CategoryStatus.AMBIGUOUS


def test_numbers_in_clarifying_question_map_to_categories() -> None:
    assert normalize_menu_number("1") == "specialist"
    assert normalize_menu_number("2") == "club"
    assert normalize_menu_number("Выбираю 3") == "international"
    assert normalize_menu_number("4") == "client"
    assert normalize_menu_number("5") is None
    assert normalize_menu_number("ничего") is None


def test_category_decision_defaults() -> None:
    decision = CategoryDecision(status=CategoryStatus.AMBIGUOUS)
    assert not decision.is_confident
    assert decision.category is None
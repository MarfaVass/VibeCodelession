"""Тесты пошаговых сценариев предварительных заявок (автомат BookingFlow)."""

from __future__ import annotations

import pytest

from bot.booking.flow import FIELD_SPECS, FlowAction, FlowStep, new_booking_flow
from bot.categorize import CATEGORY_LABELS


def _walk(flow, messages):
    """Прогнать список сообщений через сценарий, вернуть последний результат."""

    result = None
    for message in messages:
        result = flow.handle(message)
    return result


@pytest.mark.parametrize("category", ["specialist", "club", "international", "client"])
def test_every_category_has_full_scenario(category: str) -> None:
    """Все четыре категории проходят путь от имени до подтверждения."""

    flow = new_booking_flow(category)
    fields_count = len(FIELD_SPECS[category])
    steps = ["Имя Фамилия", "телефон +7 900 000-00-09", "моя просьба"]
    steps.extend(["значение"] * fields_count)
    steps.append("да")

    result = _walk(flow, steps)
    assert result.action == FlowAction.SUBMIT
    assert flow.data.name == "Имя Фамилия"
    assert flow.data.contact


def test_intro_contains_disclaimer() -> None:
    flow = new_booking_flow("client")
    intro = flow.prompt_with_intro()
    assert "предварительн" in intro.lower()
    assert "/cancel" in intro
    assert "Как вас зовут" in intro


def test_name_step_rejects_garbage() -> None:
    flow = new_booking_flow("client")
    result = flow.handle("123456")
    assert result.action == FlowAction.ASK
    assert flow.step == FlowStep.NAME
    assert flow.data.name == ""


def test_contact_step_rejects_non_contact() -> None:
    flow = new_booking_flow("client")
    flow.handle("Иван Иванов")
    for bad in ["привет", "а"]:
        result = flow.handle(bad)
        assert result.action == FlowAction.ASK
        assert flow.step == FlowStep.CONTACT
    assert flow.handle("vk.com/id123").action == FlowAction.ASK  # контакт принят


def test_optional_fields_can_be_skipped() -> None:
    flow = new_booking_flow("client")
    _walk(flow, ["Иван Иванов", "+79000000000", "пропустить", "-", "-", "-"])
    assert flow.data.request_text == ""
    assert flow.handle("да").action == FlowAction.SUBMIT
    # необязательные поля не попадают в детализацию
    assert "имя" not in {key.lower() for key in flow.data.details}


def test_required_field_cannot_be_skipped() -> None:
    flow = new_booking_flow("club")  # название организации — обязательное поле
    _walk(flow, ["Ольга Смирнова", "+79000000000", "запуск направления"])
    result = flow.handle("пропустить")
    assert "Обязательно нужно указать" in result.answer
    assert flow.step == FlowStep.FIELD


def test_summary_shows_all_data_and_disclaimer() -> None:
    flow = new_booking_flow("specialist")
    _walk(flow, ["Анна Петрова", "+79000000000", "уточнить программу",
                 "Matwork 2", "действующий тренер", "очно"])
    flow.step = FlowStep.CONFIRM
    summary = flow.data.summary()
    assert "Анна Петрова" in summary
    assert "+79000000000" in summary
    assert CATEGORY_LABELS["specialist"] in summary
    assert "представитель Академии" in summary


def test_confirm_yes_submits() -> None:
    flow = new_booking_flow("client")
    _walk(flow, ["Иван Иванов", "vk.com/id1", "-", "-", "-", "-"])
    assert flow.handle("да").action == FlowAction.SUBMIT


def test_confirm_no_cancels() -> None:
    flow = new_booking_flow("client")
    _walk(flow, ["Иван Иванов", "vk.com/id1", "-", "-", "-", "-"])
    assert flow.handle("нет").action == FlowAction.CANCELLED


def test_cancel_command_any_step() -> None:
    cases = {
        "client": ["Иван Иванов"],
        "specialist": ["Анна Петрова", "+79000000000", "вопрос про обучение"],
    }
    for category, messages in cases.items():
        flow = new_booking_flow(category)
        for message in messages:
            flow.handle(message)
        assert flow.handle("/cancel").action == FlowAction.CANCELLED


def test_question_during_flow_is_intercepted() -> None:
    """Вопрос клиента не меняет шаг и помечается как ANSWERED."""

    flow = new_booking_flow("specialist")
    flow.handle("Анна Петрова")
    for question in ["Сколько длится обучение?", "а можно онлайн?", "Подскажите цены"]:
        result = flow.handle(question)
        assert result.action == FlowAction.ANSWERED, question
        assert flow.step == FlowStep.CONTACT
    resumed = flow.resume_after_answer()
    assert resumed.action == FlowAction.ASK
    assert "контакт" in resumed.answer.lower()


def test_international_scenario_questions_are_english() -> None:
    """Вопросы английского сценария не содержат случайной кириллицы."""

    flow = new_booking_flow("international")
    flow.handle("John Smith")
    questions = [flow.current_question()]
    flow.handle("john@example.com")
    questions.append(flow.current_question())
    flow.handle("a seminar for our team")
    questions.append(flow.current_question())
    flow.handle("one-day intensive")
    questions.append(flow.current_question())

    # имя и контакт заданы по-русски; вопросы полей — на английском
    for question in questions[-2:]:
        assert question.strip()
        assert all(ord(ch) < 0x0400 for ch in question), question


def test_unknown_category_rejected() -> None:
    with pytest.raises(ValueError):
        new_booking_flow("alien")
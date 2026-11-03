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
    """Вопросы категорийных полей английского сценария без кириллицы:

    страна, организация, формат мероприятия, тема или пожелания,
    предполагаемые сроки — все необязательные (частному лицу организация
    не нужна).
    """

    flow = new_booking_flow("international")
    assert flow.handle("John Smith").action == FlowAction.ASK
    assert flow.handle("john@example.com").action == FlowAction.ASK
    assert flow.handle("a seminar for our team").action == FlowAction.ASK

    questions = []
    while flow.step == FlowStep.FIELD:
        questions.append(flow.current_question())
        flow.handle("-")
    assert len(questions) == 5, len(questions)
    assert questions[0].startswith("Which country")
    for question in questions:
        assert question.strip()
        # кириллица — U+0400..U+04FF; типографские тире/пунктуация не считаются
        assert not any(0x0400 <= ord(ch) <= 0x04FF for ch in question), question
    # все пять полей необязательны: пропуск приведёт к подтверждению
    assert flow.step == FlowStep.CONFIRM


def test_unknown_category_rejected() -> None:
    with pytest.raises(ValueError):
        new_booking_flow("alien")


def test_last_field_answer_leads_to_summary_not_bare_question() -> None:
    """После последнего поля показывается сводка (CONFIRM), а не голый вопрос.

    Было: переход на подтверждение отсылал FlowAction.ASK без сводки —
    анкета визуально зависала, а прикреплённая inline-клавиатура с
    one_time вызывала VKAPIError_911.
    """

    flow = new_booking_flow("client")
    _walk(flow, ["Иван Иванов", "vk.com/id1", "хочу курс", "-", "-", "обсудим"])
    assert flow.step == FlowStep.CONFIRM


def test_international_wish_answer_also_shows_summary() -> None:
    """Ответ на последнее поле («обсудим» и т.п.) приводит к сводке в любой ветке."""

    flow = new_booking_flow("club")
    _walk(flow, ["Ольга Смирнова", "+79000000000", "запуск направления",
                 "Fit Life, Уфа", "Ольга Смирнова", "12", "Matwork 1", "обсудим"])
    assert flow.step == FlowStep.CONFIRM
    summary = flow.data.summary()
    assert "Fit Life, Уфа" in summary
    assert "Отправить заявку" in summary
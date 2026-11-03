"""Диалоговые сценарии менеджера: приветствие, кнопки, ветки, заявки.

Логика после переработки: приветствие → выбор направления КНОПКОЙ →
диалог в ветке (RAG) → заявка. Свободный текст до выбора направления не
классифицируется; модель вызывается только внутри ветки.
"""

from __future__ import annotations

import pytest

from conftest import FakeAI
from bot import keyboards
from bot.manager import (
    CHOOSE_DIRECTION,
    DIAGNOSTIC_FOOTER,
    DialogueManager,
    INSUFFICIENT_INFO,
    SWITCH_CONFIRM,
    WELCOME,
)


def reps_text(replies) -> str:
    """Все тексты replies одной строкой (для assert'ов)."""

    return " ".join(r.text for r in replies)


@pytest.mark.asyncio
async def test_first_message_greets_with_four_buttons(manager_factory) -> None:
    """Первое сообщение: приветствие с представлением и четыре кнопки."""

    manager = manager_factory(FakeAI())
    replies = await manager.handle_message(1, "Привет")
    assert len(replies) == 1
    text, kb = replies[0].text, replies[0].keyboard
    assert "Smart Body Academy" in text
    assert "виртуальный помощник" in text.lower()
    assert kb is not None
    for cat in ("specialist", "club", "international", "client"):
        assert f'"category": "{cat}"' in kb


@pytest.mark.asyncio
async def test_greeting_not_repeated_on_followup_messages(manager_factory) -> None:
    """Второе и последующие сообщения после приветствия — без него."""

    manager = manager_factory(FakeAI())
    replies = await manager.handle_message(1, "Привет")
    assert WELCOME == replies[0].text
    replies = await manager.handle_message(1, "Что-то ещё")
    assert WELCOME not in [r.text for r in replies]
    assert "виртуальный помощник" not in " ".join(r.text.lower() for r in replies)


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["specialist", "club", "international", "client"])
async def test_each_direction_selectable_via_button(manager_factory,
                                                    category: str) -> None:
    """Каждая из четырёх кнопок переводит в свою ветку."""

    manager = manager_factory(FakeAI())
    await manager.handle_message(1, "/start")
    replies = await manager.handle_message(1, None, payload={"category": category})
    assert manager.state(1).category == category
    markers = {
        "specialist": "инструктора pilates",
        "club": "фитнес-клубами",
        "international": "international partner",
        "client": "персональных тренировках pilates",
    }
    joined = " ".join(r.text for r in replies).lower()
    assert markers[category] in joined
    assert replies[0].keyboard is not None
    # кнопки ветки: заявка + выбор другого направления
    assert "/book" in replies[0].keyboard
    assert "/menu" in replies[0].keyboard


@pytest.mark.asyncio
async def test_free_text_before_selection_does_not_classify(manager_factory) -> None:
    """Свободный текст ДО выбора направления не запускает классификацию."""

    manager = manager_factory(FakeAI(unavailable=True))
    replies = await manager.handle_message(1, "Хочу записаться на тренировку")
    assert manager.ai.calls == [], "до выбора ветки модель вызываться не должна"
    assert manager.state(1).category is None
    assert WELCOME == replies[0].text

    # повторный свободный текст — предложение выбрать кнопку
    replies = await manager.handle_message(1, "Какие у вас цены?")
    assert manager.ai.calls == []
    assert CHOOSE_DIRECTION == replies[0].text
    assert replies[0].keyboard is not None


@pytest.mark.asyncio
async def test_category_persists_between_messages(manager_factory) -> None:
    """Выбранная ветка сохраняется между сообщениями."""

    manager = manager_factory(FakeAI(answer="Матворк 1 — 40 000 р."))
    await manager.handle_message(1, None, payload={"category": "specialist"})
    assert manager.state(1).category == "specialist"
    await manager.handle_message(1, "сколько стоит обучение Matwork 1?")
    assert manager.state(1).category == "specialist"
    replies = await manager.handle_message(1, "а что входит в программу?")
    assert manager.state(1).category == "specialist"
    # вопросы попали в модель в рамках ветки
    assert len(manager.ai.calls) == 2


@pytest.mark.asyncio
async def test_answers_use_selected_category_and_common_knowledge(manager_factory) -> None:
    """Вопрос в ветке ищет фрагменты выбранной категории (+ общие материалы).

    Знания других категорий в контекст не попадают.
    """

    manager = manager_factory(FakeAI(answer="Ответ Академии."))
    await manager.handle_message(1, None, payload={"category": "club"})
    await manager.handle_message(1, "какая стоимость семинара для нашего клуба?")
    context = manager.ai.calls[0]["context"]
    assert "350 000" in context  # клубная цена из категории club
    assert "15 000" not in context  # тариф «Премиум» из ветки частных клиентов


@pytest.mark.asyncio
async def test_no_invented_answer_without_fragments(manager_factory) -> None:
    """Если подтверждённой информации нет — заготовленный честный ответ."""

    manager = manager_factory(FakeAI(answer="Модель сказала бы лишнее."))
    await manager.handle_message(1, None, payload={"category": "club"})
    replies = await manager.handle_message(1, "какая завтра погода в Москве?")
    assert manager.ai.calls == [], "модель не должна вызываться без фрагментов"
    assert INSUFFICIENT_INFO in replies[0].text


@pytest.mark.asyncio
async def test_other_direction_button_returns_to_main_menu(manager_factory) -> None:
    """Кнопка «Выбрать другое направление» (cmd /menu) открывает главное меню."""

    kb = keyboards.category_keyboard("client")
    # get_json экранирует кириллицу (\uXXXX), поэтому проверяем payload
    assert '"/menu"' in kb
    assert "book" in kb

    manager = manager_factory(FakeAI())
    await manager.handle_message(1, "Привет")
    await manager.handle_message(1, None, payload={"category": "client"})
    replies = await manager.handle_message(1, None, payload={"cmd": "/menu"})
    assert manager.state(1).category is None
    assert manager.state(1).flow is None
    assert WELCOME != replies[0].text  # приветствие не повторяется
    kb = replies[0].keyboard
    assert kb is not None and '"category": "specialist"' in kb and '"category": "client"' in kb


@pytest.mark.asyncio
async def test_switch_direction_during_booking_asks_confirmation(manager_factory) -> None:
    """При смене направления во время заполнения бот сначала уточняет."""

    manager = manager_factory(FakeAI())
    await manager.handle_message(1, None, payload={"category": "specialist"})
    await manager.handle_message(1, "/book")
    await manager.handle_message(1, "Анна Петрова")  # заявка в процессе

    # попытка сменить направление кнопкой
    replies = await manager.handle_message(1, None, payload={"category": "club"})
    assert SWITCH_CONFIRM in reps_text(replies)
    assert manager.state(1).category == "specialist"  # ветка пока прежняя
    assert manager.state(1).pending_switch == "club"

    # «нет» — заполнение продолжается с того же шага
    replies = await manager.handle_message(1, "нет")
    assert "продолжаем заполнение" in reps_text(replies).lower()
    assert manager.state(1).category == "specialist"

    # «да» — черновик отброшен, заявка не сохранена, открывается новая ветка
    replies = await manager.handle_message(1, None, payload={"category": "club"})
    replies = await manager.handle_message(1, "да")
    assert "фитнес-клубами" in reps_text(replies).lower()
    assert manager.state(1).pending_switch is None
    assert manager.db.count_bookings() == 0


@pytest.mark.asyncio
async def test_start_returns_to_choice_without_repeated_greeting(manager_factory) -> None:
    """/start возвращает к выбору направлений без повторного приветствия."""

    manager = manager_factory(FakeAI())
    # первое обращение через /start — полное приветствие
    replies = await manager.handle_message(1, "/start")
    assert WELCOME == replies[0].text

    await manager.handle_message(1, None, payload={"category": "client"})
    replies = await manager.handle_message(1, "/start")
    assert WELCOME not in [r.text for r in replies]
    assert replies[0].keyboard is not None
    assert manager.state(1).category is None


@pytest.mark.asyncio
async def test_booking_only_available_inside_branch(manager_factory) -> None:
    """/book до выбора направления не запускает сценарий заявки."""

    manager = manager_factory(FakeAI())
    await manager.handle_message(1, "Привет")
    replies = await manager.handle_message(1, "/book")
    assert manager.state(1).flow is None
    assert "выберите направление" in reps_text(replies).lower()
    assert manager.db.count_bookings() == 0


@pytest.mark.asyncio
async def test_booking_button_starts_matching_scenario(manager_factory) -> None:
    """Кнопка «Оставить заявку» в ветке запускает сценарий этой ветки."""

    manager = manager_factory(FakeAI())
    await manager.handle_message(1, None, payload={"category": "client"})
    replies = await manager.handle_message(1, None, payload={"cmd": "/book"})
    assert manager.state(1).flow is not None
    assert manager.state(1).flow.category == "client"
    joined = reps_text(replies)
    assert "предварительн" in joined.lower()
    assert "Как вас зовут" in joined


@pytest.mark.asyncio
async def test_booking_confirm_and_cancel(manager_factory) -> None:
    """Подтверждение сохраняет заявку, кнопка «Отменить» отменяет."""

    manager = manager_factory(FakeAI(unavailable=True))
    await manager.handle_message(1, None, payload={"category": "specialist"})
    await manager.handle_message(1, None, payload={"cmd": "/book"})
    for step in ["Анна Петрова", "+7 900 000-00-02", "-", "-", "-", "-"]:
        await manager.handle_message(1, step)
    replies = await manager.handle_message(1, None, payload={"cmd": "confirm_yes"})
    assert "№" in reps_text(replies) and "предварительн" in reps_text(replies)
    record = manager.db.get_latest_booking(1)
    assert record is not None and record.category == "specialist"
    assert record.name == "Анна Петрова"

    # отмена на новом сценарии
    await manager.handle_message(1, None, payload={"cmd": "/book"})
    await manager.handle_message(1, "Пётр Смирнов")
    replies = await manager.handle_message(1, None, payload={"cmd": "/cancel"})
    assert "отмен" in reps_text(replies).lower()
    assert manager.state(1).flow is None
    assert manager.db.count_bookings() == 1  # сохранённая заявка не удалена


@pytest.mark.asyncio
async def test_decline_at_confirmation_saves_nothing(manager_factory) -> None:
    """«нет» на подтверждении не сохраняет заявку."""

    manager = manager_factory(FakeAI(unavailable=True))
    await manager.handle_message(1, None, payload={"category": "club"})
    await manager.handle_message(1, "/book")
    for step in ["Ольга Смирнова", "+7 900 000-00-03", "-", "Fit Life, Уфа",
                 "Ольга Смирнова", "12", "Matwork 1", "-"]:
        await manager.handle_message(1, step)
    replies = await manager.handle_message(1, "нет")
    assert "не отправлена" in reps_text(replies) or "отмен" in reps_text(replies).lower()
    assert manager.db.count_bookings() == 0


@pytest.mark.asyncio
async def test_question_during_booking_gets_answer_and_continues(manager_factory) -> None:
    """Попутный вопрос в ветке Specialist получает RAG-ответ, сценарий продолжается."""

    manager = manager_factory(FakeAI(answer="Matwork 1 длится 3 дня."))
    await manager.handle_message(1, None, payload={"category": "specialist"})
    await manager.handle_message(1, "/book")
    await manager.handle_message(1, "Анна Петрова")
    replies = await manager.handle_message(1, "А сколько длится обучение Matwork 1?")
    texts = [r.text for r in replies]
    assert "3 дня" in texts[0]
    assert "контакт" in texts[1].lower()


@pytest.mark.asyncio
async def test_ollama_unreachable_still_replies(manager_factory) -> None:
    """Недоступность Ollama не валит диалог: готовое сообщение и предложение заявки."""

    manager = manager_factory(FakeAI(unavailable=True))
    await manager.handle_message(1, None, payload={"category": "club"})
    replies = await manager.handle_message(1, "какая цена семинара для нашего клуба?")
    assert "временно не работает" in reps_text(replies).lower()
    assert "/book" in reps_text(replies)


@pytest.mark.asyncio
async def test_db_failure_does_not_crash_bot(manager_factory) -> None:
    """Недоступность базы данных даёт сообщение об ошибке, а не крушение."""

    manager = manager_factory(FakeAI(unavailable=True))
    await manager.handle_message(1, None, payload={"category": "specialist"})
    await manager.handle_message(1, "/book")
    for step in ["Анна Петрова", "+7 900 000-00-04", "-", "-", "-", "-"]:
        await manager.handle_message(1, step)
    manager.db.db_path.unlink()
    manager.db.db_path.mkdir()  # путь теперь папка: sqlite упадёт
    replies = await manager.handle_message(1, "да")
    assert "не удалось сохранить" in reps_text(replies).lower()


@pytest.mark.asyncio
async def test_confirm_button_payload_only_with_active_flow(manager_factory) -> None:
    """Кнопка «Отправить» без активной заявки ничего не сохраняет."""

    manager = manager_factory(FakeAI())
    replies = await manager.handle_message(1, None, payload={"cmd": "confirm_yes"})
    assert manager.db.count_bookings() == 0
    assert "нет" in reps_text(replies).lower()


@pytest.mark.asyncio
async def test_diagnostic_mention_gets_action_hint(manager_factory) -> None:
    """Вопрос о первой тренировке/диагностике получает понятное следующее действие.

    Ссылку на диагностику не придумываем: на сайте Академии такой страницы нет,
    поэтому вместо кнопки-URL добавляется приписка с существующим сценарием
    заявки.
    """

    manager = manager_factory(FakeAI(answer="Диагностика проходит на первой встрече."))
    await manager.handle_message(1, None, payload={"category": "client"})
    replies = await manager.handle_message(1, "как проходит первая тренировка?")
    text = DIAGNOSTIC_FOOTER
    assert text in replies[0].text
    assert "/book" in replies[0].text
    assert "Оставить заявку" in replies[0].text
    # ссылки-выдумки нет: в ответе не должно быть URL на «диагностику»
    assert "http" not in replies[0].text


@pytest.mark.asyncio
async def test_diagnostic_hint_only_for_client_branch(manager_factory) -> None:
    """Приписка про диагностику добавляется только в ветке частных клиентов."""

    manager = manager_factory(FakeAI(answer="Упоминание диагностики для тренеров."))
    await manager.handle_message(1, None, payload={"category": "specialist"})
    replies = await manager.handle_message(1, "как проходит обучение и диагностика?")
    assert DIAGNOSTIC_FOOTER not in replies[0].text


@pytest.mark.asyncio
async def test_diagnostic_hint_absent_when_topic_not_raised(manager_factory) -> None:
    """Обычный вопрос без упоминания диагностики не получает приписку."""

    manager = manager_factory(FakeAI(answer="Стандарт — 10 000 р. за час."))
    await manager.handle_message(1, None, payload={"category": "client"})
    replies = await manager.handle_message(1, "сколько стоит тренировка?")
    assert DIAGNOSTIC_FOOTER not in replies[0].text


def test_no_diagnostics_page_in_knowledge_sources(kb) -> None:
    """В базе знаний нет ссылки на страницу «диагностики» — она не существует
    на smartbodyacademy.ru; кнопки-ссылки не добавляются без источника."""

    known_pages = {
        "https://smartbodyacademy.ru/main",
        "https://smartbodyacademy.ru/course",
        "https://smartbodyacademy.ru/trener",
        "https://smartbodyacademy.ru/club",
        "https://smartbodyacademy.ru/foreign",
        "https://smartbodyacademy.ru/training",
        "https://smartbodyacademy.ru/faq",
        "https://smartbodyacademy.ru/about",
    }
    for docs in kb.docs.values():
        for doc in docs:
            assert doc.source in known_pages
            assert "diagnostic" not in doc.source
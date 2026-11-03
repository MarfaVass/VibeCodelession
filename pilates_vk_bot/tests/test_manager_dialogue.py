"""Диалоговые сценарии менеджера: категории, уточнения, переключения, заявки."""

from __future__ import annotations

import pytest

from conftest import ClassificationAI, FakeAI
from bot.manager import DialogueManager, INSUFFICIENT_INFO


@pytest.mark.asyncio
async def test_start_greets_and_offers_directions(manager_factory) -> None:
    manager = manager_factory()
    replies = await manager.handle_message(1, "/start")
    text = " ".join(r.text for r in replies)
    assert "Smart Body Academy" in text
    assert "что вас интересует" in text.lower()
    assert replies[0].keyboard is not None and "specialist" in replies[0].keyboard


@pytest.mark.asyncio
async def test_each_category_is_routed(manager_factory) -> None:
    """Свободный текст по каждой категории попадает в свой раздел."""

    cases = [
        ("Хочу стать тренером, интересует обучение и сертификацию", "specialist"),
        ("У нас в клубе нужно обучение сотрудников семинаром", "club"),
        ("We are an international academy and invite Andrey for a seminar", "international"),
        ("Хочу записаться на персональные тренировки пробное занятие", "client"),
    ]
    for text, category in cases:
        manager = manager_factory(FakeAI())
        replies = await manager.handle_message(42, text)
        assert manager.state(42).category == category, text
        joined = " ".join(r.text for r in replies)
        markers = {
            "specialist": "частного специалиста",
            "club": "фитнес-клубами",
            "international": "international partner",
            "client": "персональных тренировках",
        }
        assert markers[category] in joined, text


@pytest.mark.asyncio
async def test_rag_sends_only_fragments_to_model(manager_factory) -> None:
    manager = manager_factory(FakeAI(answer="Ответ Академии."))
    await manager.handle_message(1, "сколько стоит обучение Matwork 1")
    fake = manager.ai  # type: ignore[attr-defined]
    assert fake.calls, "AI должен был быть вызван"
    call = fake.calls[0]
    context = call["context"]
    assert "Matwork 1" in context
    assert "Фрагмент" in context
    assert len(context) < 6000, "модель не должна получать всю базу знаний"


@pytest.mark.asyncio
async def test_ambiguous_query_asks_clarifying_question(manager_factory) -> None:
    manager = manager_factory(ClassificationAI("ambiguous"))
    replies = await manager.handle_message(1, "Здравствуйте, хорошо ли всё?")
    joined = " ".join(r.text for r in replies)
    assert "Подскажите, пожалуйста" in joined
    assert manager.state(1).category is None


@pytest.mark.asyncio
async def test_ai_classification_fallback(manager_factory) -> None:
    """Ключевые слова не сработали (неоднозначный текст), AI определил клиента."""

    manager = manager_factory(ClassificationAI("client"))
    replies = await manager.handle_message(1, "хочу начать заниматься и что-то с осанкой")
    assert manager.state(1).category == "client"
    # Ключевые слова тут неоднозначны -> AI был вызван
    assert manager.ai.calls  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_switch_category_via_menu(manager_factory) -> None:
    manager = manager_factory(FakeAI())
    await manager.handle_message(1, "Хочу стать тренером, курс обучения")
    assert manager.state(1).category == "specialist"
    await manager.handle_message(1, "/menu")
    replies = await manager.handle_message(1, None, payload={"category": "client"})
    assert manager.state(1).category == "client"
    assert any("персональн" in r.text.lower() for r in replies)


@pytest.mark.asyncio
async def test_insufficient_info_reply_when_no_fragments(manager_factory) -> None:
    manager = manager_factory(FakeAI(answer="Модель сказала бы лишнее"))
    await manager.handle_message(1, "/menu")
    await manager.handle_message(1, None, payload={"category": "club"})
    replies = await manager.handle_message(1, "какая завтра погода в Москве?")
    joined = " ".join(r.text for r in replies)
    assert INSUFFICIENT_INFO in joined


@pytest.mark.asyncio
async def test_booking_full_cycle_and_saved(manager_factory, tmp_path) -> None:
    manager = manager_factory(FakeAI(unavailable=True))  # AI не нужен для заявки
    # выбрать категорию кнопкой
    await manager.handle_message(1, None, payload={"category": "specialist"})
    await manager.handle_message(1, "/book")

    steps = ["Анна Петрова", "+7 900 000-00-02", "интересует Matwork 2",
             "Matwork 2", "тренер общего профиля", "очно в Москве", "да"]
    last = None
    for step in steps:
        replies = await manager.handle_message(1, step)
        last = replies
    joined = " ".join(r.text for r in replies)
    assert "№" in joined and "предварительн" in joined

    record = manager.db.get_latest_booking(1)
    assert record is not None
    assert record.category == "specialist"
    assert record.name == "Анна Петрова"
    assert record.contact == "+7 900 000-00-02"
    assert record.details["интересующее направление"] == "Matwork 2"
    assert record.status == "preliminary"


@pytest.mark.asyncio
async def test_booking_cancel_during_flow(manager_factory) -> None:
    manager = manager_factory()
    await manager.handle_message(1, None, payload={"category": "client"})
    await manager.handle_message(1, "/book")
    await manager.handle_message(1, "Иван Иванов")
    replies = await manager.handle_message(1, "/cancel")
    assert any("отменяю" in r.text.lower() for r in replies)
    assert manager.state(1).flow is None
    assert manager.db.count_bookings() == 0


@pytest.mark.asyncio
async def test_booking_declined_at_confirm(manager_factory) -> None:
    manager = manager_factory()
    await manager.handle_message(1, None, payload={"category": "club"})
    await manager.handle_message(1, "/book")
    for step in ["Ольга Смирнова", "+7 900 000-00-03", "запуск направления",
                 "Fit Life, Уфа", "Ольга Смирнова", "12", "Matwork 1", "-"]:
        replies = await manager.handle_message(1, step)
    replies = await manager.handle_message(1, "нет")
    assert any("не отправлена" in r.text or "отмен" in r.text.lower() for r in replies)
    assert manager.db.count_bookings() == 0


@pytest.mark.asyncio
async def test_question_during_booking_gets_answer_and_continues(manager_factory) -> None:
    manager = manager_factory(FakeAI(answer="Matwork 1 длится 3 дня."))
    await manager.handle_message(1, None, payload={"category": "specialist"})
    await manager.handle_message(1, "/book")
    await manager.handle_message(1, "Анна Петрова")
    replies = await manager.handle_message(1, "А сколько длится обучение Matwork 1?")
    texts = [r.text for r in replies]
    assert "3 дня" in texts[0]  # ответ AI
    assert "Как вас зовут" in texts[1] or "контакт" in texts[1].lower()


@pytest.mark.asyncio
async def test_ollama_unreachable_still_replies(manager_factory) -> None:
    manager = manager_factory(FakeAI(unavailable=True))
    await manager.handle_message(1, None, payload={"category": "club"})
    replies = await manager.handle_message(1, "какая цена семинара для нашего клуба?")
    joined = " ".join(r.text for r in replies)
    assert "временно не работает" in joined.lower()
    assert "/book" in joined  # бот остаётся жив и предлагает заявку


@pytest.mark.asyncio
async def test_db_failure_does_not_crash_bot(manager_factory) -> None:
    manager = manager_factory(FakeAI(unavailable=True))
    await manager.handle_message(1, None, payload={"category": "specialist"})
    await manager.handle_message(1, "/book")
    for step in ["Анна Петрова", "+7 900 000-00-04", "-", "Matwork 1", "-", "-"]:
        replies = await manager.handle_message(1, step)
    # ломаем базу: делаем файл недоступным
    manager.db.db_path.unlink()
    manager.db.db_path.mkdir()  # путь теперь папка -> sqlite упадёт
    replies = await manager.handle_message(1, "да")
    assert any("не удалось сохранить" in r.text.lower() or "базы данных" in r.text.lower()
               for r in replies)


@pytest.mark.asyncio
async def test_confirm_button_payload(manager_factory) -> None:
    """Кнопка «Отправить» на шаге подтверждения сохраняет заявку."""

    manager = manager_factory()
    await manager.handle_message(1, None, payload={"category": "client"})
    await manager.handle_message(1, "/book")
    for step in ["Иван Иванов", "vk.com/id77", "-", "-", "-", "-"]:
        await manager.handle_message(1, step)
    replies = await manager.handle_message(1, None, payload={"cmd": "confirm_yes"})
    joined = " ".join(r.text for r in replies)
    assert "№" in joined
    assert manager.db.count_bookings() == 1
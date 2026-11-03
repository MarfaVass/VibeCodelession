"""Тесты обратной связи пользователя при обработке вопросов.

Проверяется логика ``run_with_wait_note``: быстрый ответ не получает
промежуточных сообщений, медленный — ровно одно уведомление. Индикатор
набора VK (messages.setActivity) проверяется вручную в сообществе —
требует реального API.
"""

from __future__ import annotations

import asyncio

import pytest

from bot.main import AI_NOTE_DELAY, WAITING_NOTE, run_with_wait_note


class Notifier:
    """Счётчик отправленных промежуточных сообщений."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def __call__(self) -> None:
        self.sent.append(WAITING_NOTE)


async def test_fast_answer_sends_no_notice() -> None:
    """Ответ быстрее порога — уведомление не отправляется."""

    notifier = Notifier()

    async def fast():
        await asyncio.sleep(0.01)
        return ["готово"]

    result = await run_with_wait_note(fast(), send_note=notifier, note_delay=0.5)
    assert result == ["готово"]
    assert notifier.sent == []


async def test_slow_answer_sends_exactly_one_notice() -> None:
    """Долгая обработка — ровно одно сообщение перед ответом (без повторов)."""

    notifier = Notifier()

    async def slow():
        await asyncio.sleep(0.3)
        return ["полный ответ"]

    result = await run_with_wait_note(slow(), send_note=notifier, note_delay=0.05)
    assert result == ["полный ответ"]
    assert notifier.sent == [WAITING_NOTE], notifier.sent


async def test_notice_delay_respects_threshold() -> None:
    """Порог настраиваемый: обработка дольше порога — уведомление есть."""

    notifier = Notifier()

    async def medium():
        await asyncio.sleep(0.2)
        return "ok"

    result = await run_with_wait_note(medium(), send_note=notifier, note_delay=1.0)
    assert result == "ok"
    assert notifier.sent == []  # быстрее порога в 1.0 с — без уведомления


async def test_failed_answer_after_notice_still_raises() -> None:
    """Если после уведомления обработка падает, исключение не глотается."""

    notifier = Notifier()

    async def failing():
        await asyncio.sleep(0.2)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await run_with_wait_note(failing(), send_note=notifier, note_delay=0.05)
    assert notifier.sent == [WAITING_NOTE]


def test_note_delay_threshold_is_sane() -> None:
    """Порог заметного ожидания — в разумных пределах для клиентского чата."""

    assert 2.0 <= AI_NOTE_DELAY <= 10.0
"""Общие помощники для обработчиков."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

PAGE_SIZE = 10


async def safe_answer(callback: CallbackQuery, text: str | None = None) -> None:
    """callback.answer() без падения при истёкшем/неизвестном callback."""
    try:
        await callback.answer(text)
    except TelegramBadRequest:
        pass


async def leave_scenario(state: FSMContext) -> bool:
    """Завершает активный FSM-сценарий при переходе пользователя в другой раздел.

    Управляемая очистка (в отличие от state.clear()):
      1) читаем данные до очистки;
      2) стираем активное состояние и временные данные незавершённого
         сценария (черновик задачи, purpose редактирования/админ-ввода);
      3) восстанавливаем ТОЛЬКО навигационные данные: last_list (контекст
         исходного списка) и search_text (чтобы продолжал работать поиск
         и его пагинация после возврата в меню).

    Возвращает True, если сценарий был активен (для уведомления
    «Незавершённый сценарий отменён»).
    """
    data = await state.get_data()
    was_active = (await state.get_state() is not None) or bool(data)
    nav = {
        key: value for key in ("last_list", "search_text")
        if (value := data.get(key))
    }
    await state.clear()
    if nav:
        await state.set_data(nav)
    return was_active


async def nav_context(state: FSMContext | None) -> str | None:
    """last_list из FSM-данных, если он корректен ('kind' или 'kind:value').

    Некорректный/отсутствующий контекст → None (безопасный fallback
    в общий список).
    """
    if state is None:
        return None
    raw = (await state.get_data()).get("last_list")
    if isinstance(raw, str) and raw.count(":") in (1, 2):
        return raw
    return None


async def clear_fsm(state: FSMContext) -> None:
    """Корректная очистка состояния FSM после завершения сценария."""
    await state.clear()


def total_pages(total_items: int, page_size: int = PAGE_SIZE) -> int:
    """Число страниц пагинации."""
    return max(1, (total_items + page_size - 1) // page_size)

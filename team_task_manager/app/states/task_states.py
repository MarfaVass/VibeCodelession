"""Состояния FSM (aiogram.fsm.state) для пошаговых сценариев.

Создание задачи (AddTaskStates) и ввод произвольных значений при
редактировании/администрировании (ValueInputStates).
"""

from aiogram.fsm.state import State, StatesGroup


class AddTaskStates(StatesGroup):
    """Пошаговое создание задачи: название → описание → категория →
    приоритет → исполнитель → дедлайн → подтверждение."""

    title = State()
    description = State()
    category = State()
    priority = State()
    assignee = State()
    due_date = State()
    confirm = State()


class ValueInputStates(StatesGroup):
    """Универсальный ввод текстового значения (FSM «одного шага»).

    Используется для: редактирования названия/описания/дедлайна,
    добавления справочников, переименования, поиска задач.
    Поле 'purpose' в данных состояния отличает сценарии.
    """

    waiting_value = State()

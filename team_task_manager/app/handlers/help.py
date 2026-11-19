"""Справка: команда /help и кнопка «Помощь»."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..keyboards.main_menu import back_to_menu
from .helpers import leave_scenario, safe_answer

router = Router(name="help")

HELP_TEXT = (
    "❓ <b>Справка TEAM TASK MANAGER</b>\n\n"
    "<b>Команды</b>\n"
    "• /start — приветствие и главное меню\n"
    "• /add — создать задачу (пошагово)\n"
    "• /my — мои назначенные задачи\n"
    "• /list — все задачи с фильтрами (от старых к новым)\n"
    "• /stats — статистика по базе\n"
    "• /list_csv — выгрузка CSV\n"
    "• /export_excel — выгрузка XLSX (3 листа)\n"
    "• /help — эта справка\n\n"
    "<b>Как создать задачу</b>\n"
    "Нажмите «➕ Добавить задачу». Бот спросит название, описание, категорию, "
    "приоритет, исполнителя и дедлайн. Описание, исполнителя и дедлайн "
    "можно пропустить.\n\n"
    "<b>Изменение статуса</b>\n"
    "Откройте карточку задачи из любого списка и нажмите «📍 Статус». "
    "Задача, помеченная завершающим статусом («Выполнена», «Отменена»), "
    "считается закрытой; участник команды не может вернуть её в работу — "
    "это делает администратор.\n\n"
    "<b>Права</b>\n"
    "• Администратор: полное управление, справочники, удаление задач.\n"
    "• Участник: создание задач, работа со своими назначенными задачами.\n\n"
    "<b>Формат дедлайна</b>\n"
    "25.11.2026, 2026-11-25 или слова «сегодня», «завтра», «послезавтра».\n\n"
    "Если что-то не работает — напишите администратору команды."
)


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await leave_scenario(state)
    await message.answer(HELP_TEXT, reply_markup=back_to_menu())


@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery, state: FSMContext) -> None:
    await leave_scenario(state)
    if callback.message:
        await callback.message.edit_text(HELP_TEXT, reply_markup=back_to_menu())
    await safe_answer(callback)

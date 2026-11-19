"""Обработчики запуска и главного меню: /start и кнопка «Меню»."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..keyboards.main_menu import main_menu
from .helpers import leave_scenario, safe_answer

router = Router(name="start")
logger = logging.getLogger(__name__)

WELCOME = (
    "👋 <b>Добро пожаловать в TEAM TASK MANAGER!</b>\n\n"
    "Бот помогает команде создавать задачи, распределять их "
    "и следить за выполнением.\n\n"
    "Что можно делать:\n"
    "• ➕ <b>Добавить задачу</b> — пошаговое создание (текст, категория, "
    "приоритет, исполнитель, дедлайн)\n"
    "• 📋 <b>Мои задачи</b> — только те, что назначены вам\n"
    "• 📄 <b>Все задачи</b> — общий список с пагинацией\n"
    "• 🔍 <b>Поиск</b> — по названию и описанию\n"
    "• 📊 <b>Статистика</b> — сводные показатели по базе\n"
    "• 📤 <b>Экспорт</b> — CSV и Excel выгрузки\n\n"
    "Команды: /start, /add, /my, /list, /stats, /list_csv, /export_excel, /help"
)


async def _open_main_menu(target: Message, state: FSMContext, is_admin: bool) -> None:
    """Переход в главное меню с завершением незавершённого FSM-сценария.

    leave_scenario() сохраняет навигационные данные (last_list, search_text),
    остальное стирается — следующий текст пользователя не перехватится
    старым сценарием, новый сценарий начнётся с чистыми данными.
    """
    interrupted = await leave_scenario(state)
    note = "✖️ Незавершенный сценарий отменен.\n\n" if interrupted else ""
    await target.answer(note + WELCOME, reply_markup=main_menu(is_admin=is_admin))
    if interrupted:
        logger.info("Незавершённый FSM-сценарий отменён при переходе в меню")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user_db: dict) -> None:
    """Приветствие + главное меню (содержимое зависит от роли)."""
    await _open_main_menu(message, state, user_db["role"] == "admin")
    logger.info("Пользователь id=%s открыл /start", message.from_user.id)


@router.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext, user_db: dict) -> None:
    """Возврат в главное меню по кнопке (тоже завершает сценарий)."""
    interrupted = await leave_scenario(state)
    if callback.message:
        message = callback.message
        if message.text is not None:
            # Редактируем существующее сообщение, где это возможно.
            await message.edit_text(
                "🏠 <b>Главное меню</b>", reply_markup=main_menu(is_admin=user_db["role"] == "admin")
            )
            # Сценарий был активен: сообщаем об отмене отдельным сообщением —
            # основной текст уже перезаписан экраном меню.
            if interrupted:
                await message.answer("✖️ Незавершенный сценарий отменен.")
        else:
            note = "✖️ Незавершенный сценарий отменен.\n\n" if interrupted else ""
            await callback.message.answer(
                note + "🏠 <b>Главное меню</b>",
                reply_markup=main_menu(is_admin=user_db["role"] == "admin"),
            )
    await safe_answer(callback)

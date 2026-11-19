"""Обработчик статистики /stats (и кнопки «Статистика»)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..services.statistics_service import StatisticsService
from ..keyboards.main_menu import back_to_menu
from ..utils.validators import clamp_text
from .helpers import leave_scenario, safe_answer

router = Router(name="statistics")
logger = logging.getLogger(__name__)


@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext,
                    statistics_service: StatisticsService) -> None:
    await leave_scenario(state)
    text = clamp_text(await statistics_service.format_text())
    await message.answer(text, reply_markup=back_to_menu())
    logger.info("Пользователь id=%s запросил статистику", message.from_user.id)


@router.callback_query(F.data == "menu:stats")
async def cb_stats(callback: CallbackQuery, state: FSMContext,
                   statistics_service: StatisticsService) -> None:
    await leave_scenario(state)
    text = clamp_text(await statistics_service.format_text())
    if callback.message:
        await callback.message.edit_text(text, reply_markup=back_to_menu())
    await safe_answer(callback)

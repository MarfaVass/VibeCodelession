"""Сценарий создания задачи (FSM) и команда /add.

Последовательность: название → описание (можно пропустить) → категория →
приоритет → исполнитель (можно пропустить) → дедлайн (можно пропустить) →
подтверждение → сохранение в SQLite.

Справочные значения (категории, приоритеты, исполнители) читаются
из БД прямо в момент шага — в коде нет зашитых названий.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..keyboards import task_keyboards as tk
from ..keyboards.main_menu import main_menu
from ..states.task_states import AddTaskStates
from ..utils.dates import deadline_to_iso, parse_deadline
from ..utils.validators import validate_description, validate_title
from .helpers import clear_fsm, safe_answer

router = Router(name="tasks")
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Старт сценария
# ----------------------------------------------------------------------
async def _start_creation(message_target: Message, state: FSMContext) -> None:
    await state.set_state(AddTaskStates.title)
    await state.update_data(title=None, description=None, category_id=None,
                            priority_id=None, assignee_id=None, due_date=None)
    await message_target.answer(
        "➕ <b>Создание задачи — шаг 1 из 6</b>\n\n"
        "Введите <b>название</b> задачи (3–100 символов).",
        reply_markup=tk.fsm_cancel_keyboard(),
    )


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    await _start_creation(message, state)


@router.callback_query(F.data == "menu:add")
async def cb_add(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message:
        await _start_creation(callback.message, state)
    await safe_answer(callback)


@router.callback_query(F.data == "fsm:cancel")
async def cb_fsm_cancel(callback: CallbackQuery, state: FSMContext, user_db: dict) -> None:
    """Универсальная отмена любого FSM-сценария."""
    await clear_fsm(state)
    if callback.message:
        await callback.message.answer(
            "✖️ Действие отменено.", reply_markup=main_menu(user_db["role"] == "admin")
        )
    await safe_answer(callback, "Отменено")


# ----------------------------------------------------------------------
# Текстовые шаги: название, описание, дедлайн
# ----------------------------------------------------------------------
@router.message(AddTaskStates.title, F.text)
async def step_title(message: Message, state: FSMContext) -> None:
    error = validate_title(message.text or "")
    if error:
        await message.answer(f"⚠️ {error}")
        return
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(AddTaskStates.description)
    await message.answer(
        "📄 <b>Шаг 2 из 6.</b>\n\nВведите <b>описание</b> задачи — "
        "или нажмите «Пропустить».",
        reply_markup=tk.fsm_skip_keyboard(),
    )


@router.message(AddTaskStates.description, F.text)
async def step_description(message: Message, state: FSMContext, settings_repo) -> None:
    error = validate_description(message.text or "")
    if error:
        await message.answer(f"⚠️ {error}")
        return
    await state.update_data(description=(message.text or "").strip())
    await _ask_category(message, state, settings_repo)


@router.callback_query(AddTaskStates.description, F.data == "stp:skip")
async def cb_skip_description(callback: CallbackQuery, state: FSMContext,
                              settings_repo) -> None:
    await state.update_data(description="")
    if callback.message:
        await _ask_category(callback.message, state, settings_repo)
    await safe_answer(callback)


@router.message(AddTaskStates.due_date, F.text)
async def step_due_date(message: Message, state: FSMContext, timezone_name: str) -> None:
    parsed = parse_deadline(message.text or "", timezone_name)
    if parsed is None:
        await message.answer(
            "⚠️ Не удалось распознать дату.\nПримеры: 25.11.2026, 2026-11-25, завтра."
        )
        return
    await state.update_data(due_date=deadline_to_iso(parsed, timezone_name))
    await _show_confirmation(message, state)


@router.callback_query(AddTaskStates.due_date, F.data == "stp:skip")
async def cb_skip_due(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(due_date=None)
    if callback.message:
        await _show_confirmation(callback.message, state)
    await safe_answer(callback)


# ----------------------------------------------------------------------
# Справочные шаги (выбор кнопками)
# ----------------------------------------------------------------------
async def _ask_category(message: Message, state: FSMContext, settings_repo) -> None:
    await state.set_state(AddTaskStates.category)
    categories = [(c["name"], c["id"])
                  for c in await settings_repo.list_categories(only_active=True)]
    if not categories:
        await message.answer(
            "⚠️ В справочнике нет активных категорий. Попросите администратора добавить."
        )
        await clear_fsm(state)
        return
    await message.answer(
        "🗂 <b>Шаг 3 из 6.</b>\n\nВыберите <b>категорию</b> задачи:",
        reply_markup=tk.choice_keyboard(categories, "dir:cat"),
    )


@router.callback_query(AddTaskStates.category, F.data.startswith("dir:cat:"))
async def cb_pick_category(callback: CallbackQuery, state: FSMContext, settings_repo) -> None:
    loader = lambda: settings_repo.list_categories(only_active=True)  # noqa: E731
    if await _maybe_paginate(callback, "dir:cat", loader):
        return
    category = await settings_repo.get_category(int(callback.data.rsplit(":", 1)[1]))
    await state.update_data(category_id=category["id"], category_name=category["name"])
    await state.set_state(AddTaskStates.priority)
    priorities = [(p["name"], p["id"])
                  for p in await settings_repo.list_priorities(only_active=True)]
    if callback.message:
        await callback.message.answer(
            "⚡ <b>Шаг 4 из 6.</b>\n\nВыберите <b>приоритет</b> задачи:",
            reply_markup=tk.choice_keyboard(priorities, "dir:prio"),
        )
    await safe_answer(callback, "Выбрано")


@router.callback_query(AddTaskStates.priority, F.data.startswith("dir:prio:"))
async def cb_pick_priority(callback: CallbackQuery, state: FSMContext, users_repo,
                           settings_repo) -> None:
    loader = lambda: settings_repo.list_priorities(only_active=True)  # noqa: E731
    if await _maybe_paginate(callback, "dir:prio", loader):
        return
    priority = await settings_repo.get_priority(int(callback.data.rsplit(":", 1)[1]))
    await state.update_data(priority_id=priority["id"], priority_name=priority["name"])
    await state.set_state(AddTaskStates.assignee)
    users = await users_repo.list_active() or []
    rows = [[InlineKeyboardButton(text=u["full_name"], callback_data=f"dir:usr:{u['id']}")]
            for u in users]
    rows.append([InlineKeyboardButton(text="🚫 Не назначать", callback_data="stp:noassignee")])
    if callback.message:
        await callback.message.answer(
            "👥 <b>Шаг 5 из 6.</b>\n\nВыберите <b>ответственного</b>:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    await safe_answer(callback, "Выбрано")


@router.callback_query(AddTaskStates.assignee, F.data == "stp:noassignee")
async def cb_no_assignee(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(assignee_id=None, assignee_name="не назначен")
    await state.set_state(AddTaskStates.due_date)
    await _ask_due_date(callback.message)
    await safe_answer(callback)


@router.callback_query(AddTaskStates.assignee, F.data.startswith("dir:usr:"))
async def cb_pick_assignee(callback: CallbackQuery, state: FSMContext, users_repo) -> None:
    assignee_id = int(callback.data.rsplit(":", 1)[1])
    assignee = await users_repo.get(assignee_id)
    await state.update_data(
        assignee_id=assignee_id, assignee_name=assignee["full_name"] if assignee else "—"
    )
    await state.set_state(AddTaskStates.due_date)
    await _ask_due_date(callback.message)
    await safe_answer(callback, "Выбрано")


async def _ask_due_date(message: Message | None) -> None:
    if not message:
        return
    await message.answer(
        "📅 <b>Шаг 6 из 6.</b>\n\nВведите <b>дедлайн</b> (25.11.2026, 2026-11-25, "
        "завтра) — или нажмите «Пропустить».",
        reply_markup=tk.fsm_skip_keyboard(),
    )


# ----------------------------------------------------------------------
# Подтверждение и сохранение
# ----------------------------------------------------------------------
async def _show_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lines = [
        "📋 <b>Проверьте данные задачи:</b>",
        "",
        f"<b>{data['title']}</b>",
    ]
    if data.get("description"):
        lines.append(f"📝 {data['description']}")
    lines += [
        f"🗂 Категория: {data.get('category_name', '—')}",
        f"⚡ Приоритет: {data.get('priority_name', '—')}",
        f"🎯 Исполнитель: {data.get('assignee_name', 'не назначен')}",
        f"📅 Дедлайн: {data.get('due_date') or '—'}",
        "",
        "Создать задачу?",
    ]
    await message.answer("\n".join(lines), reply_markup=tk.confirm_create_keyboard())


@router.callback_query(F.data == "conf:yes")
async def cb_confirm_save(callback: CallbackQuery, state: FSMContext,
                          task_service, timezone_name: str) -> None:
    """Финальное подтверждение: сохранение задачи в SQLite."""
    data = await state.get_data()
    # Защита от повторного нажатия «Создать» (дубликат задачи невозможен:
    # после первого сохранения состояние уже очищено).
    if not data.get("title"):
        await safe_answer(callback, "Сценарий уже завершён")
        return
    task_id = await task_service.create_task(
        title=data["title"],
        description=data.get("description") or "",
        category_id=data["category_id"],
        priority_id=data["priority_id"],
        assigned_to=data.get("assignee_id"),
        due_date_iso=data.get("due_date"),
        user_id=callback.from_user.id,
        timezone_name=timezone_name,
    )
    task = await task_service.get_task(task_id)
    await clear_fsm(state)
    logger.info("Пользователь id=%s создал задачу id=%s", callback.from_user.id, task_id)
    if callback.message and task:
        card = task_service.format_task_card(task, timezone_name)
        # Карточка может превышать лимит при длинных полях — обрезаем.
        card = card[:3900]
        await callback.message.edit_text(
            f"✅ <b>Задача #{task_id} сохранена!</b>\n\n{card}",
            reply_markup=tk.task_card_keyboard(
                task_id, can_edit=True, can_delete=False, can_change_status=True
            ),
        )
    await safe_answer(callback, "Сохранено")


# ----------------------------------------------------------------------
# Помощник пагинации справочников
# ----------------------------------------------------------------------
async def _maybe_paginate(callback: CallbackQuery, prefix: str, loader) -> bool:
    """Если callback — запрос страницы списка, перерисовывает клавиатуру.

    Возвращает True, если запрос обработан.
    """
    callback_data = callback.data or ""
    if ":page:" not in callback_data:
        return False
    page = int(callback_data.rsplit(":", 1)[1])
    items = [(i["name"], i["id"]) for i in await loader()]
    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=tk.choice_keyboard(items, prefix, page=page)
        )
    await safe_answer(callback)
    return True

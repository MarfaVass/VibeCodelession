"""Просмотр задач: /list, /my, фильтры, поиск, пагинация.

/list по ТЗ показывает задачи по дате создания от старых к новым.
Пагинация по 10 записей. Поддерживаемые фильтры:
  все, мои, по категории, по статусу, по приоритету, просроченные,
  выполненные, поиск по названию и описанию.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..keyboards import task_keyboards as tk
from ..states.task_states import ValueInputStates
from ..utils.dates import is_overdue
from ..utils.validators import clamp_text
from .helpers import PAGE_SIZE, clear_fsm, leave_scenario, safe_answer, total_pages

router = Router(name="lists")
logger = logging.getLogger(__name__)

FILTER_LABELS = {
    "all": "Все задачи",
    "my": "Мои задачи",
    "over": "Просроченные",
    "done": "Выполненные",
}


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ----------------------------------------------------------------------
# Входные точки: /list, /my, кнопки меню
# ----------------------------------------------------------------------
@router.message(Command("list"))
async def cmd_list(message: Message, state: FSMContext, user_db: dict) -> None:
    await leave_scenario(state)
    await _show_filters(message)


@router.callback_query(F.data == "menu:all")
async def cb_all(callback: CallbackQuery, state: FSMContext) -> None:
    await leave_scenario(state)
    if callback.message:
        await _show_filters(callback.message)
    await safe_answer(callback)


@router.message(Command("my"))
async def cmd_my(message: Message, state: FSMContext, task_service, user_db: dict,
                 timezone_name: str) -> None:
    await leave_scenario(state)
    await _render_list(message, task_service, user_db, timezone_name, "my", 0,
                       state=state)


@router.callback_query(F.data == "menu:my")
async def cb_my(callback: CallbackQuery, state: FSMContext, task_service,
                user_db: dict, timezone_name: str) -> None:
    await leave_scenario(state)
    if callback.message:
        await _render_list(callback.message, task_service, user_db,
                           timezone_name, "my", 0, state=state)
    await safe_answer(callback)


@router.callback_query(F.data == "menu:search")
async def cb_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ValueInputStates.waiting_value)
    await state.update_data(purpose="search")
    if callback.message:
        await callback.message.answer(
            "🔍 <b>Поиск задач</b>\n\nВведите текст для поиска по названию "
            "и описанию:",
            reply_markup=tk.fsm_cancel_keyboard(),
        )
    await safe_answer(callback)


@router.message(ValueInputStates.waiting_value, F.text)
async def step_search_text(message: Message, state: FSMContext, task_service,
                           user_db: dict, timezone_name: str) -> None:
    """Универсальный шаг ввода значения; здесь — текст поиска."""
    data = await state.get_data()
    if data.get("purpose") != "search":
        # Ввод относится к другому сценарию — передаём дальше.
        raise SkipHandler()
    await clear_fsm(state)
    search_text = (message.text or "").strip()
    if not search_text:
        await message.answer("⚠️ Поисковый запрос не может быть пустым.")
        return
    # Текст поиска хранится в FSM, чтобы кнопки страниц помнили запрос.
    await state.update_data(purpose="search", search_text=search_text)
    await _render_list(message, task_service, user_db, timezone_name,
                       "srch", 0, search_text=search_text)


# ----------------------------------------------------------------------
# Фильтры
# ----------------------------------------------------------------------
async def _show_filters(message: Message) -> None:
    rows = [
        [InlineKeyboardButton(text=f"📄 {FILTER_LABELS['all']}", callback_data="flt:all")],
        [InlineKeyboardButton(text=f"📋 {FILTER_LABELS['my']}", callback_data="flt:my")],
        [InlineKeyboardButton(text="📍 По статусу", callback_data="flt:sta")],
        [InlineKeyboardButton(text="🗂 По категории", callback_data="flt:cat")],
        [InlineKeyboardButton(text="⚡ По приоритету", callback_data="flt:prio")],
        [InlineKeyboardButton(text=f"⚠️ {FILTER_LABELS['over']}", callback_data="flt:over")],
        [InlineKeyboardButton(text=f"✅ {FILTER_LABELS['done']}", callback_data="flt:done")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")],
    ]
    await message.answer("🔎 <b>Просмотр задач</b>\n\nВыберите фильтр:",
                         reply_markup=_kb(rows))


@router.callback_query(F.data.startswith("flt:"))
async def cb_pick_filter(callback: CallbackQuery, state: FSMContext,
                         task_service, user_db: dict,
                         timezone_name: str, settings_repo) -> None:
    """Разбор callback фильтра:
    flt:<kind>            — kind из {all,my,over,done} или вид справочника;
    flt:<kind>:<id>       — конкретное значение справочника.
    """
    await leave_scenario(state)
    parts = (callback.data or "").split(":")
    kind = parts[1] if len(parts) > 1 else "all"

    if kind in {"all", "my", "over", "done"}:
        await _render_list(callback.message, task_service, user_db,
                           timezone_name, kind, 0, state=state)
        await safe_answer(callback)
        return

    if len(parts) == 2:
        # Показываем список значений справочника для фильтра.
        loaders = {
            "sta": ("📍 Выберите статус:", settings_repo.list_statuses),
            "cat": ("🗂 Выберите категорию:", settings_repo.list_categories),
            "prio": ("⚡ Выберите приоритет:", settings_repo.list_priorities),
        }
        title, loader = loaders.get(kind, ("Выберите значение:",
                                           settings_repo.list_categories))
        items = await loader(only_active=True)
        if callback.message:
            if callback.message.text is not None:
                # Редактируем экран фильтра — без размножения сообщений (N8).
                await callback.message.edit_text(
                    f"{title}\n\nВыберите значение:",
                    reply_markup=tk.choice_keyboard(
                        [(i["name"], i["id"]) for i in items], f"flt:{kind}",
                    ),
                )
            else:
                await callback.message.answer(
                    f"{title}\n\nВыберите значение:",
                    reply_markup=tk.choice_keyboard(
                        [(i["name"], i["id"]) for i in items], f"flt:{kind}",
                    ),
                )
        await safe_answer(callback)
        return

    target = f"{kind[:3]}:{parts[2]}"
    await _render_list(callback.message, task_service, user_db,
                       timezone_name, target, 0, state=state)
    await safe_answer(callback)


# ----------------------------------------------------------------------
# Пагинация и формирование списка
# ----------------------------------------------------------------------
def _parse_filter_key(raw: str) -> tuple[str, dict[str, Any]]:
    """'my' → ('my', {}); 'sta:3' → ('sta', {'status_id': 3})."""
    kind, _, value = raw.partition(":")
    mapping = {"sta": "status_id", "cat": "category_id", "prio": "priority_id"}
    kwargs: dict[str, Any] = {}
    if kind in mapping and value.isdigit():
        kwargs[mapping[kind]] = int(value)
    return kind, kwargs


@router.callback_query(F.data.startswith("list:"))
async def cb_list_page(callback: CallbackQuery, task_service, user_db: dict,
                       timezone_name: str, state: FSMContext) -> None:
    """callback формата list:<filter_key>:<page>."""
    _, filter_key, page_raw = (callback.data or "list:all:0").split(":", 2)
    if not page_raw.isdigit():
        await safe_answer(callback)
        return
    search_text = None
    if filter_key == "srch":
        search_text = (await state.get_data()).get("search_text")
        if not search_text:
            if callback.message:
                await callback.message.answer(
                    "⚠️ Строка поиска устарела — повторите поиск через 🔍."
                )
            await safe_answer(callback)
            return
    await _render_list(callback.message, task_service, user_db, timezone_name,
                       filter_key, int(page_raw), search_text=search_text,
                       state=state)
    await safe_answer(callback)


async def _render_list(message: Message | None, task_service, user_db: dict,
                       timezone_name: str, filter_key: str, page: int,
                       search_text: str | None = None,
                       state: FSMContext | None = None) -> None:
    """Собирает одну страницу списка задач с кнопками пагинации."""
    if message is None:
        return
    kind, extra = _parse_filter_key(filter_key)
    kwargs: dict[str, Any] = {
        "order": "asc",  # по ТЗ /list: от старых к новым
        "limit": PAGE_SIZE,
        "offset": page * PAGE_SIZE,
        **extra,
    }
    label = FILTER_LABELS.get(kind, "Задачи")
    if kind == "my":
        kwargs["assigned_to"] = user_db["id"]
    elif kind == "over":
        kwargs["only_overdue"] = True
    elif kind == "done":
        kwargs["only_completed"] = True
    if search_text:
        kwargs["search_text"] = search_text
        label = f"Поиск «{search_text}»"

    page_size = kwargs.pop("limit")
    page_offset = kwargs.pop("offset")
    total = await task_service.tasks.list_tasks(count_only=True, **kwargs)
    tasks = await task_service.tasks.list_tasks(
        limit=page_size, offset=page_offset, **kwargs
    )
    pages = total_pages(total)

    # Запоминаем контекст списка для возврата «⬅️ К списку» из карточки
    # задачи (функцией cb_task читается из FSM). Обновляется на каждом
    # рендере страницы — при смене списка/страницы старый контекст
    # перезаписывается, не остаётся от предыдущего списка.
    if state is not None:
        await state.update_data(last_list=f"{filter_key}:{page}")

    if not tasks:
        text = f"📭 <b>{label}</b>\n\nЗадач не найдено."
        rows = [[InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")]]
        await _send_or_edit(message, text, _kb(rows))
        return

    lines = [f"📋 <b>{label}</b> — всего {total}", "", f"Страница {page + 1} из {pages}", ""]
    rows: list[list[InlineKeyboardButton]] = []
    for index, task in enumerate(tasks, start=page * PAGE_SIZE + 1):
        marker = "⚠️ " if is_overdue(task.get("due_date"),
                                     bool(task["status_is_final"]), timezone_name) else ""
        title = clamp_text(task["title"], 40)
        lines.append(f"{index}. {marker}[{task['status']}] #{task['id']} {title}")
        rows.append([InlineKeyboardButton(
            text=f"#{task['id']} {title}", callback_data=f"task:{task['id']}",
        )])
    lines.append("\nНажмите кнопку, чтобы открыть карточку задачи.")

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️",
                                             callback_data=f"list:{filter_key}:{page - 1}"))
    if pages > 1:
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{pages}", callback_data=f"list:{filter_key}:{page}"))
    if page < pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️",
                                             callback_data=f"list:{filter_key}:{page + 1}"))
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")])

    await _send_or_edit(message, clamp_text("\n".join(lines)), _kb(rows))


async def _send_or_edit(message: Message, text: str, keyboard: InlineKeyboardMarkup) -> None:
    """Правит существующее сообщение, если оно текстовое; иначе отправляет новое."""
    if message.text is not None:
        try:
            await message.edit_text(text, reply_markup=keyboard)
            return
        except Exception:
            pass  # не удалось отредактировать — отправляем новое
    if message.bot is not None:
        await message.answer(text, reply_markup=keyboard)

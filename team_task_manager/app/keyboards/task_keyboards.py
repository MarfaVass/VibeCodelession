"""Клавиатуры сценариев задач: создание, список с пагинацией, карточка.

Форматы callback_data:
  * fsm:cancel            — отмена сценария создания/редактирования;
  * dir:<id>              — выбор элемента справочника в FSM (dir = cat|prio|usr);
  * stp:cat|prio|usr|skip — пропуск шага FSM;
  * list:<fkey>:<page>    — пагинация списка (fkey — ключ фильтра);
  * task:<id>             — открыть карточку задачи;
  * tst:<id>:<status_id>  — сменить статус;
  * tpr:<id>:<prio_id>    — сменить приоритет;
  * tas:<id>:<user_id>    — назначить исполнителя;
  * ted:<id> / tdel:<id> / this:<id> — редактирование, удаление, история.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def fsm_cancel_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены текущего FSM-сценария."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="fsm:cancel")]]
    )


def confirm_create_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение создания задачи (после ввода всех шагов FSM)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Создать", callback_data="conf:yes"),
        InlineKeyboardButton(text="✖️ Отмена", callback_data="fsm:cancel"),
    ]])


def fsm_skip_keyboard(skip_label: str = "Пропустить") -> InlineKeyboardMarkup:
    """Кнопки пропуска шага и отмены (для необязательных полей)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"⏭ {skip_label}", callback_data="stp:skip"),
        InlineKeyboardButton(text="✖️ Отмена", callback_data="fsm:cancel"),
    ]])


def choice_keyboard(
    items: list[tuple[str, int]], callback_prefix: str, page: int = 0, per_page: int = 8
) -> InlineKeyboardMarkup:
    """Универсальная клавиатура выбора элемента справочника с пагинацией.

    :param items: список пар (подпись, id).
    :param callback_prefix: префикс callback, например 'dir:cat'.
    """
    start = page * per_page
    chunk = items[start:start + per_page]
    rows = [[InlineKeyboardButton(text=title, callback_data=f"{callback_prefix}:{item_id}")]
            for title, item_id in chunk]
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{callback_prefix}:page:{page - 1}"))
    if start + per_page < len(items):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{callback_prefix}:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="fsm:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def list_navigation_keyboard(filter_key: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Кнопки пагинации под списком задач."""
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"list:{filter_key}:{page - 1}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"list:{filter_key}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def task_card_keyboard(task_id: int, *, can_edit: bool, can_delete: bool,
                       can_change_status: bool,
                       return_to: str | None = None) -> InlineKeyboardMarkup:
    """Кнопки под карточкой задачи — в зависимости от прав пользователя.

    :param return_to: контекст исходного списка 'filter_key:page' (из FSM),
           'sta:3:0'/'srch:0' также допустимы. Отсутствует/некорректен —
           безопасный возврат в общий список ('all:0').
    """
    back = return_to if isinstance(return_to, str) and return_to.count(":") in (1, 2) \
        else "all:0"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="ℹ️ История", callback_data=f"this:{task_id}")]
    ]
    if can_change_status:
        rows.insert(0, [InlineKeyboardButton(text="📍 Статус", callback_data=f"tstat:{task_id}")])
    if can_edit:
        rows.insert(0, [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"ted:{task_id}")])
        rows[-1].insert(0, InlineKeyboardButton(text="⚡ Приоритет", callback_data=f"tpr:{task_id}"))
    rows.append([InlineKeyboardButton(text="🎯 Исполнитель", callback_data=f"tas:{task_id}")])
    if can_delete:
        rows.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"tdel:{task_id}")])
    # Единый футер: возврат в исходный список + главное меню из карточки.
    rows.append([
        InlineKeyboardButton(text="⬅️ К списку", callback_data=f"list:{back}"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления задачи."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"tdel:yes:{task_id}"),
        InlineKeyboardButton(text="↩️ Оставить", callback_data=f"task:{task_id}"),
    ]])


def card_menu_footer(task_id: int) -> list[list[InlineKeyboardButton]]:
    """Единый футер подменю карточки: возврат к карточке + главное меню."""
    return [[
        InlineKeyboardButton(text="⬅️ К карточке", callback_data=f"task:{task_id}"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu"),
    ]]


def status_choice_keyboard(task_id: int, statuses: list[dict]) -> InlineKeyboardMarkup:
    """Выбор нового статуса для задачи."""
    rows = [[InlineKeyboardButton(text=s["name"], callback_data=f"tst:{task_id}:{s['id']}")]
            for s in statuses]
    rows.extend(card_menu_footer(task_id))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def priority_choice_keyboard(task_id: int, priorities: list[dict]) -> InlineKeyboardMarkup:
    """Выбор нового приоритета для задачи."""
    rows = [[InlineKeyboardButton(text=p["name"], callback_data=f"tpr:{task_id}:{p['id']}")]
            for p in priorities]
    rows.extend(card_menu_footer(task_id))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def assignee_choice_keyboard(task_id: int, users: list[dict]) -> InlineKeyboardMarkup:
    """Выбор исполнителя (+ кнопка «не назначена»)."""
    rows = [[InlineKeyboardButton(text=u["full_name"], callback_data=f"tas:{task_id}:{u['id']}")]
            for u in users]
    rows.append([InlineKeyboardButton(text="🚫 Не назначена", callback_data=f"tas:{task_id}:0")])
    rows.extend(card_menu_footer(task_id))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_field_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Меню выбора редактируемого поля."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Название", callback_data=f"ted:title:{task_id}")],
        [InlineKeyboardButton(text="📄 Описание", callback_data=f"ted:desc:{task_id}")],
        [InlineKeyboardButton(text="📅 Дедлайн", callback_data=f"ted:due:{task_id}")],
        *card_menu_footer(task_id),
    ])

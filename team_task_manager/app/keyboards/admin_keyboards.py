"""Клавиатуры администрирования: команда, справочники, доступ.

Форматы callback_data:
  * adm:team / adm:cat / adm:status / adm:prio / adm:access — разделы;
  * ref:<kind>:<id>       — выбрать элемент справочника (kind = cat|sta|pri);
  * refadd:<kind>         — добавить элемент (FSM);
  * refdel:<kind>:<id>    — (в меню элемента) отключить/включить;
  * refren:<kind>:<id>    — переименовать (FSM);
  * usr:<id>              — карточка участника;
  * usrr:<id>:<role>      — сменить роль;
  * usra:<id>:<flag>      — активировать/деактивировать.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def reference_item_keyboard(kind: str, item_id: int, is_active: bool,
                            used_count: int, is_used: bool) -> InlineKeyboardMarkup:
    """Меню элемента справочника.

    :param used_count: сколько задач ссылаются на элемент (для лога админу).
    :param is_used: True — элемент нельзя отключить (на него ссылаются задачи)?
                    Нет: элемент с задачами отключать МОЖНО (задачи сохраняют
                    историю), поэтому кнопка отключения всегда доступна.
    """
    toggle_label = "⛔ Отключить" if is_active else "✅ Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"refren:{kind}:{item_id}")],
        [InlineKeyboardButton(text=toggle_label, callback_data=f"refdel:{kind}:{item_id}")],
        [InlineKeyboardButton(text="⬅️ К списку", callback_data=f"adm:{kind}")],
    ])


def add_item_keyboard(kind: str) -> InlineKeyboardMarkup:
    """Кнопка добавления элемента справочника + назад."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data=f"refadd:{kind}")],
        [InlineKeyboardButton(text="⬅️ К админ-панели", callback_data="menu:admin")],
    ])


def user_card_keyboard(user_id: int, role: str, is_active: bool) -> InlineKeyboardMarkup:
    """Меню участника команды: смена роли и активности."""
    rows = [
        [InlineKeyboardButton(
            text="👑 Сделать админом" if role == "member" else "👤 Сделать участником",
            callback_data=f"usrr:{user_id}:{'admin' if role == 'member' else 'member'}",
        )],
        [InlineKeyboardButton(
            text="⛔ Деактивировать" if is_active else "✅ Активировать",
            callback_data=f"usra:{user_id}:{0 if is_active else 1}",
        )],
        [InlineKeyboardButton(text="⬅️ К команде", callback_data="adm:team")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def team_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ К админ-панели", callback_data="menu:admin")]
    ])

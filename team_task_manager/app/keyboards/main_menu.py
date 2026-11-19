"""Клавиатуры главного меню (inline-кнопки).

Формат callback_data: 'menu:<действие>'. Данные короткие —
укладываются в лимит Telegram в 64 байта.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(is_admin: bool) -> InlineKeyboardMarkup:
    """Главное меню. Администратору добавляются разделы управления."""
    rows = [
        [InlineKeyboardButton(text="➕ Добавить задачу", callback_data="menu:add")],
        [InlineKeyboardButton(text="📋 Мои задачи", callback_data="menu:my"),
         InlineKeyboardButton(text="📄 Все задачи", callback_data="menu:all")],
        [InlineKeyboardButton(text="🔍 Поиск задач", callback_data="menu:search"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")],
        [InlineKeyboardButton(text="📤 Экспорт", callback_data="menu:export"),
         InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu")]]
    )


def admin_menu() -> InlineKeyboardMarkup:
    """Панель администратора."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление командой", callback_data="adm:team")],
        [InlineKeyboardButton(text="🗂 Категории", callback_data="adm:cat")],
        [InlineKeyboardButton(text="📍 Статусы", callback_data="adm:status")],
        [InlineKeyboardButton(text="⚡ Приоритеты", callback_data="adm:prio")],
        [InlineKeyboardButton(text="🔐 Управление доступом", callback_data="adm:access")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu")],
    ])

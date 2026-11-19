"""Административный раздел (только для роли ADMIN).

Функции:
  * управление командой (роли, активация/деактивация участников);
  * справочники: категории, статусы, приоритеты — добавить,
    переименовать, включить/отключить;
  * раздел с ролью admin требует серверной проверки в КАЖДОМ
    обработчике — роли скрываются и кнопки, и функциональность.

Форматы callback_data см. в docstring admin_keyboards.py.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..keyboards import admin_keyboards as ak
from ..keyboards.main_menu import admin_menu
from ..keyboards.task_keyboards import fsm_cancel_keyboard
from ..states.task_states import ValueInputStates
from ..utils.dates import format_datetime
from .helpers import clear_fsm, safe_answer

router = Router(name="admin")
logger = logging.getLogger(__name__)

KIND_TITLES = {
    "cat": ("categories", "🗂 Справочник «Категории»"),
    "sta": ("statuses", "📍 Справочник «Статусы»"),
    "pri": ("priorities", "⚡ Справочник «Приоритеты»"),
}


def _is_admin(user_db: dict) -> bool:
    return bool(user_db and user_db.get("role") == "admin")


async def _deny(callback: CallbackQuery) -> None:
    await callback.answer("⛔ Доступно только администраторам", show_alert=True)


# ----------------------------------------------------------------------
# Панель и команда
# ----------------------------------------------------------------------
@router.callback_query(F.data == "menu:admin")
async def cb_admin(callback: CallbackQuery, user_db: dict) -> None:
    if not _is_admin(user_db):
        await _deny(callback)
        return
    if callback.message:
        await callback.message.edit_text(
            "⚙️ <b>Админ-панель</b>\n\nВыберите раздел:", reply_markup=admin_menu()
        )
    await safe_answer(callback)


@router.callback_query(F.data == "adm:team")
async def cb_team(callback: CallbackQuery, users_repo, user_db: dict) -> None:
    if not _is_admin(user_db):
        await _deny(callback)
        return
    members = await users_repo.list_all()
    lines = ["👥 <b>Команда</b>", ""]
    rows = []
    for member in members:
        mark = "✅" if member["is_active"] else "⛔"
        role = "👑 админ" if member["role"] == "admin" else "👤 участник"
        status_text = "активен" if member["is_active"] else "деактивирован"
        lines.append(f"{mark} {member['full_name']} — {role} ({status_text})")
        rows.append([F_button(f"Открыть: {member['full_name'][:30]}",
                              f"usr:{member['id']}")])
    rows.append([F_button("⬅️ К админ-панели", callback_data="menu:admin")])
    if callback.message:
        await callback.message.edit_text(
            "\n".join(lines) if members else "👥 В команде пока нет участников.",
            reply_markup=F_keyboard(rows),
        )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("usr:"))
async def cb_user_card(callback: CallbackQuery, users_repo, user_db: dict,
                       timezone_name: str) -> None:
    if not _is_admin(user_db):
        await _deny(callback)
        return
    member_id = int((callback.data or "usr:0").split(":")[1])
    member = await users_repo.get(member_id)
    if not member:
        await callback.answer("Участник не найден", show_alert=True)
        return
    active = "✅ активен" if member["is_active"] else "⛔ деактивирован"
    role = "👑 Администратор" if member["role"] == "admin" else "👤 Участник"
    joined = format_datetime(member["joined_at"], timezone_name)
    if callback.message:
        await callback.message.edit_text(
            f"👤 <b>{member['full_name']}</b>\n"
            f"Telegram ID: {member['id']}\n"
            f"Username: {member.get('username') or '—'}\n"
            f"Роль: {role}\n"
            f"Статус: {active}\n"
            f"В команде с: {joined}",
            reply_markup=ak.user_card_keyboard(member_id, member["role"],
                                                bool(member["is_active"])),
        )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("usrr:"))
async def cb_change_role(callback: CallbackQuery, users_repo, user_db: dict,
                         timezone_name: str) -> None:
    """usrr:<user_id>:<role> — сменить роль участника."""
    if not _is_admin(user_db):
        await _deny(callback)
        return
    _, member_id_raw, new_role = (callback.data or "usrr:0:member").split(":")
    if new_role not in {"admin", "member"}:
        await callback.answer("Недопустимая роль", show_alert=True)
        return
    await users_repo.set_role(int(member_id_raw), new_role)
    await callback.answer("Роль обновлена")
    # Повторно открываем карточку участника с новыми данными.
    callback.data = f"usr:{member_id_raw}"
    await cb_user_card(callback, users_repo, user_db, timezone_name)


@router.callback_query(F.data.startswith("usra:"))
async def cb_toggle_active(callback: CallbackQuery, users_repo, user_db: dict,
                           timezone_name: str) -> None:
    """usra:<user_id>:<flag> — активировать/деактивировать."""
    if not _is_admin(user_db):
        await _deny(callback)
        return
    _, member_id_raw, flag = (callback.data or "usra:0:1").split(":")
    is_active = flag == "1"
    if int(member_id_raw) == user_db["id"] and not is_active:
        await callback.answer("Нельзя деактивировать самого себя", show_alert=True)
        return
    await users_repo.set_active(int(member_id_raw), is_active)
    await callback.answer("Готово")
    callback.data = f"usr:{member_id_raw}"
    await cb_user_card(callback, users_repo, user_db, timezone_name)


@router.callback_query(F.data == "adm:access")
async def cb_access(callback: CallbackQuery, user_db: dict) -> None:
    if not _is_admin(user_db):
        await _deny(callback)
        return
    if callback.message:
        await callback.message.edit_text(
            "🔐 <b>Управление доступом</b>\n\n"
            "• Роли и активность участников — в разделе «Управление командой».\n"
            "• Первые администраторы задаются списком ADMIN_IDS в файле .env.\n"
            "• Деактивированные участники теряют доступ немедленно — бот "
            "не отвечает на их сообщения.\n"
            "• Неактивные участники не видят данные команды.",
            reply_markup=ak.team_menu_keyboard(),
        )
    await safe_answer(callback)


# ----------------------------------------------------------------------
# Справочники: просмотр, добавление, переименование, вкл/выкл
# ----------------------------------------------------------------------
async def _reference_view(settings_repo, kind: str) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и клавиатура экрана справочника (общая для callback- и message-путей)."""
    db_key, title = KIND_TITLES[kind]
    loader = {
        "categories": settings_repo.list_categories,
        "statuses": settings_repo.list_statuses,
        "priorities": settings_repo.list_priorities,
    }[db_key]
    items = await loader()
    lines = [f"<b>{title}</b>", ""]
    rows = []
    for item in items:
        mark = "" if item["is_active"] else "⛔ "
        extra = " (завершающий)" if kind == "sta" and item["is_final"] else ""
        lines.append(f"• {mark}{item['name']}{extra}")
        state_word = "вкл" if item["is_active"] else "выкл"
        rows.append([F_button(f"⚙️ {item['name'][:28]} ({state_word})",
                              f"ref:{kind}:{item['id']}")])
    rows.append([F_button("➕ Добавить элемент", callback_data=f"refadd:{kind}")])
    rows.append([F_button("⬅️ К админ-панели", callback_data="menu:admin")])
    return "\n".join(lines), F_keyboard(rows)


async def _show_reference(callback: CallbackQuery, settings_repo, kind: str) -> None:
    """Список элементов справочника с кнопками управления."""
    text, kb = await _reference_view(settings_repo, kind)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb)
    await safe_answer(callback)


@router.callback_query(F.data.in_({"adm:cat", "adm:status", "adm:prio"}))
async def cb_reference_lists(callback: CallbackQuery, settings_repo, user_db: dict) -> None:
    if not _is_admin(user_db):
        await _deny(callback)
        return
    kind = {"adm:cat": "cat", "adm:status": "sta", "adm:prio": "pri"}[callback.data]
    await _show_reference(callback, settings_repo, kind)


@router.callback_query(F.data.startswith("adm:"))
async def cb_reference_alias(callback: CallbackQuery, settings_repo, user_db: dict) -> None:
    """Возврат к списку справочника из меню элемента (adm:<kind>)."""
    kind = (callback.data or "").split(":")[1]
    if kind in KIND_TITLES:
        if not _is_admin(user_db):
            await _deny(callback)
            return
        await _show_reference(callback, settings_repo, kind)
        return
    await safe_answer(callback)


@router.callback_query(F.data.startswith("ref:"))
async def cb_item_show(callback: CallbackQuery, settings_repo, user_db: dict) -> None:
    """ref:<kind>:<id> — меню элемента справочника."""
    _, kind, item_id_raw = (callback.data or "").split(":")
    item_id = int(item_id_raw)
    db_key, title = KIND_TITLES[kind]
    loader = {
        "categories": settings_repo.list_categories,
        "statuses": settings_repo.list_statuses,
        "priorities": settings_repo.list_priorities,
    }[db_key]
    item = next((i for i in await loader() if i["id"] == item_id), None)
    if not item:
        await callback.answer("Элемент не найден", show_alert=True)
        return
    usage = await _usage_count(settings_repo, db_key, item_id)
    if callback.message:
        await callback.message.edit_text(
            f"<b>{title}</b>\n\nЭлемент: <b>{item['name']}</b>\n"
            f"{'— активен' if item['is_active'] else '— отключён (не отображается в выборе)'}\n"
            f"Задач с этим значением: {usage}",
            reply_markup=admin_keyboards_item(kind, item_id, bool(item["is_active"])),
        )
    await safe_answer(callback)


async def _usage_count(settings_repo, db_key: str, item_id: int) -> int:
    """Сколько задач ссылаются на элемент справочника."""
    tables = {"categories": ("categories", "category_id"),
              "statuses": ("statuses", "status_id"),
              "priorities": ("priorities", "priority_id")}
    table, column = tables[db_key]
    return int(await settings_repo.db.fetch_val(
        f"SELECT COUNT(*) FROM tasks WHERE {column} = ?", (item_id,)  # nosec B608
    ))


@router.callback_query(F.data.startswith("refren:"))
async def cb_rename_start(callback: CallbackQuery, state: FSMContext, user_db: dict) -> None:
    """refren:<kind>:<id> — переименование через FSM."""
    if not _is_admin(user_db):
        await _deny(callback)
        return
    _, kind, item_id_raw = (callback.data or "").split(":")
    await state.set_state(ValueInputStates.waiting_value)
    await state.update_data(purpose=f"refren:{kind}", item_id=int(item_id_raw))
    if callback.message:
        await callback.message.answer(
            "✏️ Введите новое <b>название</b>:", reply_markup=fsm_cancel_keyboard()
        )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("refdel:"))
async def cb_toggle_reference(callback: CallbackQuery, settings_repo, user_db: dict) -> None:
    """refdel:<kind>:<id> — безопасное включение/отключение (без удаления строк,
    на которых ссылаются существующие задачи)."""
    if not _is_admin(user_db):
        await _deny(callback)
        return
    _, kind, item_id_raw = (callback.data or "").split(":")
    item_id = int(item_id_raw)
    kind_full = KIND_TITLES[kind][0]
    set_active_map = {
        "categories": settings_repo.set_category_active,
        "statuses": settings_repo.set_status_active,
        "priorities": settings_repo.set_priority_active,
    }
    loader = {
        "categories": settings_repo.list_categories,
        "statuses": settings_repo.list_statuses,
        "priorities": settings_repo.list_priorities,
    }[kind_full]
    item = next((i for i in await loader() if i["id"] == item_id), None)
    if not item:
        await callback.answer("Элемент не найден", show_alert=True)
        return
    new_state = not bool(item["is_active"])
    if new_state is False and kind_full == "statuses" and item["is_final"]:
        usage = await _usage_count(settings_repo, kind_full, item_id)
        if usage:
            await callback.answer(
                f"⛔ Нельзя отключить завершающий статус «{item['name']}»: "
                f"с ним {usage} задач. Сначала переведите задачи в другой статус.",
                show_alert=True,
            )
            return
    await set_active_map[kind_full](item_id, new_state)
    await callback.answer("Включено" if new_state else "Отключено")
    callback.data = f"adm:{kind}"
    await cb_reference_lists(callback, settings_repo, user_db)


@router.callback_query(F.data.startswith("refadd:"))
async def cb_add_start(callback: CallbackQuery, state: FSMContext, user_db: dict) -> None:
    """refadd:<kind> — добавление элемента справочника через FSM."""
    if not _is_admin(user_db):
        await _deny(callback)
        return
    kind = (callback.data or "").split(":")[1]
    await state.set_state(ValueInputStates.waiting_value)
    await state.update_data(purpose=f"refadd:{kind}")
    title = KIND_TITLES.get(kind, ("", "элемент"))[1]
    if callback.message:
        await callback.message.answer(
            f"➕ Введите <b>название</b> нового элемента ({title}):",
            reply_markup=fsm_cancel_keyboard(),
        )
    await safe_answer(callback)


async def _run_reference_input(message: Message, state: FSMContext,
                               settings_repo, user_db: dict) -> bool:
    """Обработчик FSM-ввода для добавления/переименования. True — обработано.

    Ошибки ввода (пустое название, дубликат) НЕ завершают сценарий:
    пользователь остаётся в состоянии ввода с кнопкой «✖️ Отмена» и может
    повторить попытку. После успеха — возврат в список соответствующего
    справочника, а не в главное меню.
    """
    data = await state.get_data()
    purpose = data.get("purpose", "")
    name = (message.text or "").strip()
    if not name:
        await message.answer(
            "⚠️ Название не может быть пустым. Введите его повторно "
            "или нажмите «✖️ Отмена».",
            reply_markup=fsm_cancel_keyboard(),
        )
        return True  # остаёмся в состоянии, ждём повторный ввод
    kind = None
    ok = False
    if purpose.startswith("refadd:"):
        kind = purpose.split(":")[1]
        adders = {
            "cat": settings_repo.add_category,
            "sta": settings_repo.add_status,
            "pri": settings_repo.add_priority,
        }
        ok = await adders[kind](name)
    elif purpose.startswith("refren:"):
        _, kind = purpose.split(":")
        item_id = data["item_id"]
        renamers = {
            "cat": settings_repo.rename_category,
            "sta": settings_repo.rename_status,
            "pri": settings_repo.rename_priority,
        }
        ok = await renamers[kind](item_id, name)
    if ok:
        await clear_fsm(state)
        text, kb = await _reference_view(settings_repo, kind)
        await message.answer(
            "✅ Изменения справочника сохранены.\n\n" + text, reply_markup=kb
        )
        logger.info("Админ id=%s изменил справочник (%s): %s",
                    user_db["id"], purpose, name)
        return True
    # Дубликат: состояние сохраняется — можно ввести другое название.
    await message.answer(
        "⚠️ Элемент с таким названием уже существует. Введите другое название "
        "или нажмите «✖️ Отмена».",
        reply_markup=fsm_cancel_keyboard(),
    )
    return True


# ----------------------------------------------------------------------
# FSM-ввод текста распределяется по сценариям (edit-сценарии — в
# task_management.py, поиск — в lists.py). Если purpose не для справочника,
# передаём управление дальше.
# ----------------------------------------------------------------------
@router.message(ValueInputStates.waiting_value, F.text)
async def step_ref_input(message: Message, state: FSMContext,
                         settings_repo, user_db: dict) -> None:
    """Ввод названия нового элемента или переименования справочника."""
    data = await state.get_data()
    purpose = data.get("purpose", "")
    if not purpose.startswith(("refadd", "refren")):
        raise SkipHandler()
    await _run_reference_input(message, state, settings_repo, user_db)


# ----------------------------------------------------------------------
# Мини-хелперы создания кнопок (короче полного синтаксиса aiogram)
# ----------------------------------------------------------------------
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: E402


def F_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def F_keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_keyboards_item(kind: str, item_id: int, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Переименовать",
                              callback_data=f"refren:{kind}:{item_id}")],
        [InlineKeyboardButton(text="⛔ Отключить" if is_active else "✅ Включить",
                              callback_data=f"refdel:{kind}:{item_id}")],
        [InlineKeyboardButton(text="⬅️ К списку", callback_data=f"adm:{kind}")],
    ])

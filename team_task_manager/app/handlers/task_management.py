"""Управление отдельной задачей: карточка, смена статуса/приоритета/
исполнителя, редактирование полей, удаление с подтверждением, история.

Все операции проверяют права на серверной стороне через TaskService.
"""

from __future__ import annotations

import logging

from aiogram import F, Router, Bot
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..keyboards import task_keyboards as tk
from ..keyboards.main_menu import main_menu
from ..services.notification_service import NotificationService
from ..states.task_states import ValueInputStates
from ..utils.dates import deadline_to_iso, format_date, parse_deadline
from ..utils.validators import clamp_text, validate_description, validate_title
from .helpers import clear_fsm, nav_context, safe_answer

router = Router(name="task_management")
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Карточка задачи
# ----------------------------------------------------------------------
@router.callback_query(F.data.startswith("task:"))
async def cb_task(callback: CallbackQuery, state: FSMContext, task_service,
                  user_db: dict, timezone_name: str, **kwargs) -> None:
    task_id = int((callback.data or "").split(":")[1])
    task = await task_service.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    card = clamp_text(task_service.format_task_card(task, timezone_name))
    kb = tk.task_card_keyboard(
        task_id,
        can_edit=task_service.can_edit_task(user_db, task),
        can_delete=task_service.can_delete_task(user_db, task),
        can_change_status=task_service.can_change_status(user_db, task),
        return_to=await nav_context(state),
    )
    if callback.message:
        await callback.message.edit_text(card, reply_markup=kb)
    await safe_answer(callback)


# ----------------------------------------------------------------------
# Статус
# ----------------------------------------------------------------------
@router.callback_query(F.data.startswith("tstat:"))
async def cb_status_menu(callback: CallbackQuery, task_service, settings_repo,
                         user_db: dict) -> None:
    task_id = int((callback.data or "").split(":")[1])
    task = await task_service.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    # Серверная проверка прав (не только скрытие кнопок!).
    if not task_service.can_change_status(user_db, task):
        await callback.answer("⛔ Статус этой задачи изменить нельзя", show_alert=True)
        return
    statuses = await settings_repo.list_statuses(only_active=True)
    if callback.message:
        await callback.message.edit_text(
            "📍 Выберите новый <b>статус</b>:",
            reply_markup=tk.status_choice_keyboard(task_id, statuses),
        )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("tst:"))
async def cb_status_change(callback: CallbackQuery, state: FSMContext,
                           task_service, user_db: dict,
                           timezone_name: str, notification_service: NotificationService,
                           bot: Bot) -> None:
    """tst:<task_id>:<status_id> — применить новый статус."""
    _, task_id_raw, status_id_raw = (callback.data or "tst:0:0").split(":")
    task_id, status_id = int(task_id_raw), int(status_id_raw)

    task = await task_service.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    if not task_service.can_change_status(user_db, task):
        await callback.answer("⛔ Недостаточно прав", show_alert=True)
        return

    old_status, old_assignee = task["status"], task["assigned_to"]
    updated = await task_service.change_status(task_id, status_id, user_db["id"])
    if not updated:
        await callback.answer("Не удалось изменить статус", show_alert=True)
        return

    was_final = bool(task["status_is_final"])
    # Уведомления: о смене статуса автору, о завершении — автору и исполнителю.
    await notification_service.notify_status_change(bot, updated, old_status, user_db["id"])
    if updated["status_is_final"] and not was_final:
        await notification_service.notify_completion(bot, updated, user_db["id"])

    card = clamp_text(task_service.format_task_card(updated, timezone_name))
    kb = tk.task_card_keyboard(
        task_id,
        can_edit=task_service.can_edit_task(user_db, updated),
        can_delete=task_service.can_delete_task(user_db, updated),
        can_change_status=task_service.can_change_status(user_db, updated),
        return_to=await nav_context(state),
    )
    if callback.message:
        await callback.message.edit_text(card, reply_markup=kb)
    await safe_answer(callback, "Статус обновлён")


# ----------------------------------------------------------------------
# Приоритет и исполнитель
# ----------------------------------------------------------------------
@router.callback_query(F.data.regexp(r"^tpr:\d+$"))
async def cb_priority_menu(callback: CallbackQuery, settings_repo) -> None:
    task_id = int((callback.data or "tpr:0").split(":")[1])
    priorities = await settings_repo.list_priorities(only_active=True)
    if callback.message:
        await callback.message.edit_text(
            "⚡ Выберите новый <b>приоритет</b>:",
            reply_markup=tk.priority_choice_keyboard(task_id, priorities),
        )
    await safe_answer(callback)


@router.callback_query(F.data.regexp(r"^tpr:\d+:\d+$"))
async def cb_priority_change(callback: CallbackQuery, state: FSMContext,
                             task_service, user_db: dict,
                             timezone_name: str) -> None:
    _, task_id_raw, prio_raw = (callback.data or "tpr:0:0").split(":")
    task_id, priority_id = int(task_id_raw), int(prio_raw)

    task = await task_service.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    if not task_service.can_edit_task(user_db, task):
        await callback.answer("⛔ Недостаточно прав", show_alert=True)
        return

    updated = await task_service.change_priority(task_id, priority_id, user_db["id"])
    if not updated:
        await callback.answer("Не удалось изменить приоритет", show_alert=True)
        return
    await _show_card_after_update(callback, state, task_service, user_db,
                                  timezone_name, updated)


@router.callback_query(F.data.regexp(r"^tas:\d+$"))
async def cb_assignee_menu(callback: CallbackQuery, users_repo) -> None:
    task_id = int((callback.data or "tas:0").split(":")[1])
    users = await users_repo.list_active() or []
    if callback.message:
        await callback.message.edit_text(
            "🎯 Выберите <b>исполнителя</b>:",
            reply_markup=tk.assignee_choice_keyboard(task_id, users),
        )
    await safe_answer(callback)


@router.callback_query(F.data.regexp(r"^tas:\d+:\d+$"))
async def cb_assignee_change(callback: CallbackQuery, state: FSMContext,
                             task_service, user_db: dict,
                             timezone_name: str, notification_service: NotificationService,
                             bot: Bot) -> None:
    """tas:<task_id>:<user_id> (0 — снять назначение)."""
    _, task_id_raw, user_raw = (callback.data or "tas:0:0").split(":")
    task_id, assignee_id = int(task_id_raw), int(user_raw) or None

    task = await task_service.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    if not task_service.can_edit_task(user_db, task):
        await callback.answer("⛔ Недостаточно прав", show_alert=True)
        return

    old_assignee = task["assigned_to"]
    updated = await task_service.change_assignee(task_id, assignee_id, user_db["id"])
    if not updated:
        await callback.answer("Не удалось сменить исполнителя", show_alert=True)
        return
    if assignee_id != old_assignee:
        await notification_service.notify_assignment(bot, updated, old_assignee)
    await _show_card_after_update(callback, state, task_service, user_db,
                                  timezone_name, updated)


# ----------------------------------------------------------------------
# Редактирование полей
# ----------------------------------------------------------------------
@router.callback_query(F.data.regexp(r"^ted:\d+$"))
async def cb_edit_menu(callback: CallbackQuery, task_service, user_db: dict) -> None:
    task_id = int((callback.data or "ted:0").split(":")[1])
    task = await task_service.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    if not task_service.can_edit_task(user_db, task):
        await callback.answer("⛔ Редактировать эту задачу нельзя", show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text(
            f"✏️ <b>Редактирование задачи #{task_id}</b>\n\nЧто изменить?",
            reply_markup=tk.edit_field_keyboard(task_id),
        )
    await safe_answer(callback)


@router.callback_query(F.data.regexp(r"^ted:(title|desc|due):\d+$"))
async def cb_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    """Начало FSM-ввода нового значения поля."""
    _, field, task_id_raw = (callback.data or "").split(":")
    task_id = int(task_id_raw)
    await state.set_state(ValueInputStates.waiting_value)
    await state.update_data(purpose=f"edit:{field}", task_id=task_id)
    prompts = {
        "title": "Введите новое <b>название</b> задачи:",
        "desc": "Введите новое <b>описание</b> (или «-» чтобы очистить):",
        "due": "Введите новый <b>дедлайн</b> (25.11.2026, 2026-11-25, завтра); "
               "«-» чтобы убрать срок:",
    }
    if callback.message:
        await callback.message.answer(prompts[field], reply_markup=tk.fsm_cancel_keyboard())
    await safe_answer(callback)


@router.message(ValueInputStates.waiting_value, F.text)
async def step_edit_value(message: Message, state: FSMContext, task_service,
                          user_db: dict, timezone_name: str,
                          notification_service: NotificationService, bot: Bot) -> None:
    """Универсальный шаг ввода: здесь обрабатываются значения редактирования.

    Сценарии поиска/справочников обрабатываются раньше (в других роутерах),
    поэтому сюда попадает только purpose='edit:*'.
    """
    data = await state.get_data()
    purpose = data.get("purpose", "")
    if not purpose.startswith("edit:"):
        # Ввод относится к другому сценарию — передаём дальше.
        raise SkipHandler()
    # Сохраняем контекст исходного списка для возврата «⬅️ К списку»
    # из карточки после редактирования.
    last_list = data.get("last_list")
    await clear_fsm(state)
    if last_list:
        await state.update_data(last_list=last_list)
    field, task_id = purpose.split(":")[1], data["task_id"]
    text = (message.text or "").strip()

    try:
        if field == "title":
            error = validate_title(text)
            if error:
                await message.answer(f"⚠️ {error}")
                return
            updated = await task_service.edit_fields(task_id, user_db["id"], title=text)
        elif field == "desc":
            value = "" if text == "-" else text
            error = validate_description(value)
            if error:
                await message.answer(f"⚠️ {error}")
                return
            updated = await task_service.edit_fields(task_id, user_db["id"], description=value)
        elif field == "due":
            if text == "-":
                # due_date=None означает «убрать дедлайн» (см. edit_fields).
                updated = await task_service.edit_fields(task_id, user_db["id"], due_date=None)
            else:
                parsed = parse_deadline(text, timezone_name)
                if parsed is None:
                    await message.answer("⚠️ Не удалось распознать дату. "
                                         "Пример: 25.11.2026 или завтра.")
                    return
                due_iso = deadline_to_iso(parsed, timezone_name)
                updated = await task_service.edit_fields(task_id, user_db["id"],
                                                          due_date=due_iso)
        else:
            return
    except Exception as exc:
        logger.warning("Ошибка редактирования задачи %s: %s", task_id, exc)
        await message.answer("⚠️ Не удалось внести изменение. Попробуйте позже.")
        return

    if not updated:
        await message.answer("⚠️ Задача не найдена.")
        return
    await message.answer(
        f"✅ Поле обновлено.\n\n" + clamp_text(task_service.format_task_card(updated, timezone_name)),
        reply_markup=tk.task_card_keyboard(
            task_id,
            can_edit=task_service.can_edit_task(user_db, updated),
            can_delete=task_service.can_delete_task(user_db, updated),
            can_change_status=task_service.can_change_status(user_db, updated),
            return_to=last_list,
        ),
    )


# ----------------------------------------------------------------------
# Удаление
# ----------------------------------------------------------------------
@router.callback_query(F.data.startswith("tdel:") and F.data.regexp(r"^tdel:\d+$"))
async def cb_delete_confirm(callback: CallbackQuery, task_service, user_db: dict) -> None:
    task_id = int((callback.data or "tdel:0").split(":")[1])
    task = await task_service.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    if not task_service.can_delete_task(user_db, task):
        await callback.answer("⛔ Удалять задачи может только администратор",
                              show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text(
            f"⚠️ <b>Удалить задачу #{task_id} «{task['title']}»?</b>\n\n"
            "Это действие необратимо — вместе с задачей удалится её история.",
            reply_markup=tk.confirm_delete_keyboard(task_id),
        )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("tdel:yes:"))
async def cb_delete_apply(callback: CallbackQuery, task_service, user_db: dict,
                          db) -> None:
    task_id = int((callback.data or "tdel:yes:0").split(":")[2])
    task = await task_service.get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    if not task_service.can_delete_task(user_db, task):
        await callback.answer("⛔ Недостаточно прав", show_alert=True)
        return
    # Опасная операция: сначала создаём резервную копию БД.
    from ..services.backup_service import BackupService  # noqa: PLC0415
    backup_service = BackupService(db.db_path, db.db_path.parent.parent / "backups")
    await backup_service.create_backup(db.conn, f"перед удалением задачи {task_id}")

    deleted = await task_service.delete_task(task_id, user_db["id"])
    if callback.message:
        await callback.message.edit_text(
            f"🗑 Задача #{task_id} удалена.",
            reply_markup=main_menu(user_db["role"] == "admin"),
        )
    await safe_answer(callback, "Удалено" if deleted else "Уже удалена")


# ----------------------------------------------------------------------
# История изменений
# ----------------------------------------------------------------------
ACTION_LABELS = {
    "created": "создана",
    "status": "статус",
    "priority": "приоритет",
    "assignee": "исполнитель",
    "title": "название",
    "description": "описание",
    "category": "категория",
    "due_date": "дедлайн",
}


@router.callback_query(F.data.startswith("this:"))
async def cb_history(callback: CallbackQuery, task_service, timezone_name: str) -> None:
    task_id = int((callback.data or "this:0").split(":")[1])
    history = await task_service.tasks.get_history(task_id)
    lines = [f"ℹ️ <b>История задачи #{task_id}</b>", ""]
    if not history:
        lines.append("История пуста.")
    for entry in history:
        action = ACTION_LABELS.get(entry["action"], entry["action"])
        old_v = entry["old_value"] or "—"
        new_v = entry["new_value"] or "—"
        lines.append(
            f"• {format_date(entry['created_at'], timezone_name)} — "
            f"{entry.get('user_name') or '—'}: {action}: {old_v} → {new_v}"
        )
    lines.append("")
    lines.append("⬅️ Возврат к карточке кнопкой ниже.")
    kb = InlineKeyboardMarkup(inline_keyboard=tk.card_menu_footer(task_id))
    if callback.message:
        await callback.message.edit_text(clamp_text("\n".join(lines)), reply_markup=kb)
    await safe_answer(callback)


async def _show_card_after_update(callback: CallbackQuery, state: FSMContext,
                                  task_service, user_db: dict,
                                  timezone_name: str, task: dict) -> None:
    """Обновляет карточку задачи после успешного изменения."""
    if callback.message:
        await callback.message.edit_text(
            clamp_text(task_service.format_task_card(task, timezone_name)),
            reply_markup=tk.task_card_keyboard(
                task["id"],
                can_edit=task_service.can_edit_task(user_db, task),
                can_delete=task_service.can_delete_task(user_db, task),
                can_change_status=task_service.can_change_status(user_db, task),
                return_to=await nav_context(state),
            ),
        )

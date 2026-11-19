"""Обработчики экспорта: /list_csv (CSV), /export_excel (XLSX) и меню «📤 Экспорт».

Единая логика формирования и отправки — _build_and_send(); её вызывают
и команды (как раньше), и inline-кнопки меню экспорта (exp:csv / exp:xlsx).

Порядок: формируем временный файл в exports/, отправляем документом,
затем удаляем файл (в т.ч. при ошибке отправки). Экспорт — снимок базы
на момент выгрузки.
"""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..exports.csv_export import write_csv_file
from ..exports.excel_export import write_xlsx
from ..keyboards.main_menu import back_to_menu
from ..utils.validators import clamp_text
from aiogram.fsm.context import FSMContext
from .helpers import leave_scenario, safe_answer

router = Router(name="exports")
logger = logging.getLogger(__name__)

EXPORTS_DIR = Path(__file__).resolve().parents[2] / "exports"

# Нейтральные подписи: Telegram только отдаёт файл пользователю,
# место сохранения (Загрузки/Другое) определяет клиент Telegram.
CAPTIONS = {
    "csv": "📄 Выгрузка задач в формате CSV ({count} задач).\n"
           "Кодировка UTF-8 с BOM, разделитель «;» — открывается в Excel/Calc.",
    "xlsx": "📊 Выгрузка задач в формате Excel ({count} задач).\n"
            "Листы: ЗАДАЧИ, СВОДКА, СПРАВОЧНИКИ.",
}


def export_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопки скачивания файлов + возврат в главное меню."""
    rows = [
        [InlineKeyboardButton(text="📄 Скачать CSV", callback_data="exp:csv")],
        [InlineKeyboardButton(text="📊 Скачать Excel", callback_data="exp:xlsx")],
        *back_to_menu().inline_keyboard,
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _build_and_send(target: types.Message, kind: str, task_service,
                          settings_repo, statistics_service, timezone_name: str,
                          exports_dir: Path = EXPORTS_DIR) -> None:
    """Формирует файл выгрузки (csv|xlsx) и отправляет его документом.

    Общая точка для /list_csv, /export_excel и кнопок меню экспорта —
    бизнес-логика формирования файлов не дублируется.
    Пустая база не блокирует выгрузку: оба формата позволяют создать
    отчёт без задач (CSV — строка заголовков, Excel — три листа).
    """
    tasks = await task_service.tasks.all_for_export()
    if kind == "csv":
        path = write_csv_file(tasks, exports_dir, timezone_name)
    else:
        stats = await statistics_service.collect()
        dictionaries = await settings_repo.all_for_export()
        path = write_xlsx(tasks, stats, dictionaries, exports_dir, timezone_name)

    caption = CAPTIONS[kind].format(count=len(tasks))
    try:
        await target.answer_document(types.FSInputFile(path), caption=clamp_text(caption, 900))
        logger.info("Файл экспорта отправлен: %s (%d задач)", path.name, len(tasks))
    except Exception:
        # Ошибки доставки (сеть/Telegram API) не должны оставлять у
        # пользователя ощущение успеха — показываем понятное сообщение,
        # подробности в логах. Файл всё равно удаляется в finally.
        logger.exception("Не удалось отправить файл экспорта: %s", path.name)
        try:
            await target.answer(
                "⚠️ Не удалось отправить файл выгрузки. "
                "Попробуйте ещё раз — если не поможет, обратитесь к администратору."
            )
        except Exception:  # noqa: S110 — чат мог стать недоступным; не критично
            pass
    finally:
        if path.exists():
            path.unlink(missing_ok=True)
            logger.info("Временный файл экспорта удалён: %s", path.name)


# ----------------------------------------------------------------------
# Команды (сохранены как раньше, но логика переехала в _build_and_send)
# ----------------------------------------------------------------------
@router.message(F.text.startswith("/list_csv"))
async def cmd_list_csv(message: types.Message, task_service,
                       timezone_name: str, user_db: dict) -> None:
    """CSV со всеми задачами (UTF-8 BOM, разделитель ';')."""
    logger.info("Пользователь id=%s выгрузил CSV (команда)", message.from_user.id)
    await _build_and_send(message, "csv", task_service, None, None, timezone_name)


@router.message(F.text.startswith("/export_excel"))
async def cmd_export_excel(message: types.Message, task_service, settings_repo,
                           statistics_service, timezone_name: str, db) -> None:
    """XLSX с тремя листами: ЗАДАЧИ, СВОДКА, СПРАВОЧНИКИ."""
    logger.info("Пользователь id=%s выгрузил Excel (команда)", message.from_user.id)
    await _build_and_send(message, "xlsx", task_service, settings_repo,
                          statistics_service, timezone_name)


# ----------------------------------------------------------------------
# Меню экспорта и кнопки скачивания
# ----------------------------------------------------------------------
@router.callback_query(F.data == "menu:export")
async def cb_export(callback: types.CallbackQuery, state: FSMContext,
                    task_service) -> None:
    """Меню экспорта: кнопки скачивания файлов."""
    await leave_scenario(state)
    count = await task_service.tasks.count()
    empty_note = "" if count else "\n\n📭 В базе пока нет задач — файл будет содержать только заголовки."
    text = (
        "📤 <b>Экспорт данных</b>\n\n"
        f"В базе сейчас {count} задач.\n"
        "Выберите формат — бот отправит файл документом:" + empty_note
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=export_menu_keyboard())
    await safe_answer(callback)


@router.callback_query(F.data == "exp:csv")
async def cb_exp_csv(callback: types.CallbackQuery, task_service,
                     timezone_name: str, settings_repo, statistics_service) -> None:
    """Кнопка «📄 Скачать CSV»."""
    if callback.message:
        await _build_and_send(callback.message, "csv", task_service,
                              settings_repo, statistics_service, timezone_name)
    await safe_answer(callback, "Файл формируется")


@router.callback_query(F.data == "exp:xlsx")
async def cb_exp_xlsx(callback: types.CallbackQuery, task_service, settings_repo,
                      statistics_service, timezone_name: str) -> None:
    """Кнопка «📊 Скачать Excel»."""
    if callback.message:
        await _build_and_send(callback.message, "xlsx", task_service,
                              settings_repo, statistics_service, timezone_name)
    await safe_answer(callback, "Файл формируется")

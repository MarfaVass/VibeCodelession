"""Тесты обработчиков экспорта (уровень handlers, mock-объекты Telegram).

Реальные проверяемые контракты:
  * файл формируется на диске и отправляется через answer_document
    настоящим FSInputFile с именем tasks_<дата>.csv|xlsx;
  * временный файл удаляется после отправки (успех ИЛИ ошибка);
  * при ошибке отправки пользователь получает понятное сообщение;
  * пустая база отдаёт пустой отчёт документом, а не ошибку;
  * старые команды /list_csv и /export_excel работают как раньше;
  * callback-кнопки exp:csv / exp:xlsx и меню menu:export работают.

Telegram здесь фейкуется (FakeMessage/FakeCallbackQuery), но сама БД,
файлы выгрузки и код обработчиков — настоящие.
"""

from __future__ import annotations

import re
from pathlib import Path

from aiogram.types import FSInputFile, InlineKeyboardButton

from app.handlers import exports as exp


class FakeMessage:
    """Минимальная подмена aiogram Message для обработчиков экспорта."""

    def __init__(self) -> None:
        self.documents: list[tuple] = []   # (FSInputFile, caption)
        self.answers: list[str] = []

    async def answer_document(self, document, caption=None, **kwargs) -> None:
        self.documents.append((document, caption))

    async def answer(self, text, **kwargs) -> None:
        self.answers.append(text)


class BrokenMessage(FakeMessage):
    """Отправка документов падает — имитация сетевой ошибки Telegram."""

    async def answer_document(self, document, caption=None, **kwargs) -> None:
        raise ConnectionError("имитация сбоя сети при отправке")


class FakeCallbackQuery:
    """Минимальная подмена CallbackQuery c прикреплённым сообщением."""

    def __init__(self, message, data: str = "") -> None:
        self.message = message
        self.data = data
        self.alerts: list[str] = []

    async def answer(self, text=None, show_alert=False, **kwargs) -> None:
        self.alerts.append(text)


async def _create_task(task_service, settings_repo, admin_user, title="Задача для экспорта"):
    """Регистрирует одну реальную задачу в тестовой БД."""
    cat = (await settings_repo.list_categories(only_active=True))[0]
    prio = (await settings_repo.list_priorities(only_active=True))[0]
    return await task_service.create_task(
        title=title, description="Проверка экспорта", category_id=cat["id"],
        priority_id=prio["id"], assigned_to=None, due_date_iso=None,
        user_id=admin_user["id"], timezone_name="UTC",
    )


NAME_STAMP = r"tasks_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}"

# ----------------------------------------------------------------------
# Кнопки меню экспорта
# ----------------------------------------------------------------------
async def test_callback_exp_csv_sends_document(task_service, settings_repo,
                                               statistics_service, admin_user,
                                               tmp_path) -> None:
    """Callback exp:csv формирует CSV и отправляет его документом."""
    await _create_task(task_service, settings_repo, admin_user)
    fake = FakeMessage()
    cb = FakeCallbackQuery(fake, "exp:csv")

    await exp.cb_exp_csv(cb, task_service, "UTC", settings_repo, statistics_service)

    assert len(fake.documents) == 1
    document, caption = fake.documents[0]
    assert isinstance(document, FSInputFile)
    path = Path(document.path)
    assert re.search(NAME_STAMP + r".csv$", path.name)      # тип и дата в имени
    assert not path.exists()                                  # временный файл удалён
    assert "CSV" in caption and "1 задач" in caption          # нейтральная подпись
    assert cb.alerts                                          # callback подтверждён


async def test_callback_exp_xlsx_sends_document(task_service, settings_repo,
                                                statistics_service, admin_user,
                                                tmp_path) -> None:
    """Callback exp:xlsx формирует XLSX и отправляет его документом."""
    await _create_task(task_service, settings_repo, admin_user)
    fake = FakeMessage()
    cb = FakeCallbackQuery(fake, "exp:xlsx")

    await exp.cb_exp_xlsx(cb, task_service, settings_repo, statistics_service, "UTC")

    document, caption = fake.documents[0]
    assert isinstance(document, FSInputFile)
    path = Path(document.path)
    assert re.search(NAME_STAMP + r".xlsx$", path.name)
    assert not path.exists()
    assert "Excel" in caption


# ----------------------------------------------------------------------
# Команды: обратная совместимость
# ----------------------------------------------------------------------
async def test_command_list_csv_still_works(task_service, settings_repo,
                                            statistics_service, admin_user,
                                            tmp_path) -> None:
    """/list_csv продолжает отправлять CSV-документ."""
    await _create_task(task_service, settings_repo, admin_user)
    fake = FakeMessage()
    fake.from_user = type("U", (), {"id": admin_user["id"]})()

    await exp.cmd_list_csv(fake, task_service, "UTC", {"id": admin_user["id"]})

    document, _ = fake.documents[0]
    assert re.search(NAME_STAMP + r".csv$", Path(document.path).name)
    assert not Path(document.path).exists()


async def test_command_export_excel_still_works(task_service, settings_repo,
                                                statistics_service, admin_user,
                                                tmp_path) -> None:
    """/export_excel продолжает отправлять XLSX-документ."""
    await _create_task(task_service, settings_repo, admin_user)
    fake = FakeMessage()
    fake.from_user = type("U", (), {"id": admin_user["id"]})()

    await exp.cmd_export_excel(fake, task_service, settings_repo,
                               statistics_service, "UTC", task_service.db)

    document, _ = fake.documents[0]
    assert re.search(NAME_STAMP + r".xlsx$", Path(document.path).name)
    assert not Path(document.path).exists()


# ----------------------------------------------------------------------
# Ошибки отправки и пустая база
# ----------------------------------------------------------------------
async def test_temp_file_removed_on_send_error(task_service, admin_user,
                                               tmp_path) -> None:
    """Ошибка отправки: файл удалён, пользователь получил понятное сообщение."""
    fake = BrokenMessage()

    await exp._build_and_send(fake, "csv", task_service, None, None, "UTC",
                              exports_dir=tmp_path)

    assert not fake.documents
    assert any("Не удалось отправить" in text for text in fake.answers)
    leftover = list(tmp_path.glob("tasks_*.csv"))
    assert leftover == []                                     # файл удалён в anyway


async def test_empty_base_csv_sends_headers_only(task_service, tmp_path) -> None:
    """Пустая база: CSV-отчёт отправляется документом (только заголовки)."""
    fake = FakeMessage()

    await exp._build_and_send(fake, "csv", task_service, None, None, "UTC",
                              exports_dir=tmp_path)

    _, caption = fake.documents[0]
    assert "0 задач" in caption
    assert not list(tmp_path.glob("tasks_*.csv"))


async def test_empty_base_xlsx_sends_empty_report(task_service, settings_repo,
                                                  statistics_service,
                                                  tmp_path) -> None:
    """Пустая база: XLSX с тремя листами отправляется документом."""
    fake = FakeMessage()

    await exp._build_and_send(fake, "xlsx", task_service, settings_repo,
                              statistics_service, "UTC", exports_dir=tmp_path)

    _, caption = fake.documents[0]
    assert "0 задач" in caption
    assert not list(tmp_path.glob("tasks_*.xlsx"))


# ----------------------------------------------------------------------
# Меню экспорта
# ----------------------------------------------------------------------
async def test_export_menu_shows_download_buttons(task_service, tmp_path) -> None:
    """Меню menu:export предлагает кнопки скачивания CSV и Excel."""
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage

    fake = FakeMessage()
    fake.text = "текст сообщения"
    fake.edit_text = _record_edit(fake)
    cb = FakeCallbackQuery(fake, "menu:export")
    state = FSMContext(storage=MemoryStorage(),
                       key=StorageKey(bot_id=1, chat_id=1, user_id=1))

    await exp.cb_export(cb, state, task_service)

    text, reply_markup = fake.edits[0]
    buttons = [b for row in reply_markup.inline_keyboard for b in row]
    labels = [b.callback_data for b in buttons]
    assert "exp:csv" in labels and "exp:xlsx" in labels
    # Возврат в главное меню — существующий колбэк.
    assert "menu" in labels
    assert any(isinstance(b, InlineKeyboardButton) and b.text == "⬅️ В главное меню"
               for b in buttons)


def _record_edit(fake):
    edits: list[tuple] = []

    async def edit_text(text, **kwargs) -> None:
        edits.append((text, kwargs.get("reply_markup")))

    fake.edits = edits
    return edit_text

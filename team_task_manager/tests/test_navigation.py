"""Тесты навигации этапа 2.

Telegram фейкуется минимально (сообщения/колбэки), FSM — настоящий
aiogram FSMContext на MemoryStorage, БД и обработчики — реальные.

Проверяются:
  * кнопки «⬅️ К списку» / «🏠 Главное меню» в карточке и подменю;
  * контекст списка (last_list) и возврат с тем же фильтром/страницей;
  * управляемая очистка FSM при переходе в меню (с сохранением поиска);
  * пагинация поиска после меню;
  * тупики админ-справочников (пусто/дубликат/повтор/успех).
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.handlers import admin as admin_h
from app.handlers import lists as lists_h
from app.handlers import start as start_h
from app.handlers import task_management as tm
from app.keyboards import task_keyboards as tk
from app.states.task_states import AddTaskStates, ValueInputStates
from tests.test_export_handlers import FakeCallbackQuery
from tests.test_export_handlers import _create_task


def make_state() -> FSMContext:
    """Настоящий FSMContext (MemoryStorage), как в приложении."""
    return FSMContext(storage=MemoryStorage(),
                      key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def buttons_of(markup) -> list:
    return [button for row in markup.inline_keyboard for button in row]


def callbacks_of(markup) -> list[str]:
    return [b.callback_data for b in buttons_of(markup)]


class ScreenMessage:
    """Текстовое сообщение-экран: edit_text записывается в self.edits.

    edit_records содержит кортежи (текст, reply_markup).
    """

    def __init__(self) -> None:
        self.text = "существующий текст экрана"
        self.edits: list[tuple] = []
        self.answers: list[tuple] = []

    async def edit_text(self, text, reply_markup=None, **kwargs) -> None:
        self.edits.append((text, reply_markup))

    async def answer(self, text, reply_markup=None, **kwargs) -> None:
        self.answers.append((text, reply_markup))


class InputMessage:
    """Сообщение от пользователя (текстовый ввод) — только answer()."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.bot = None  # без привязки к боту: _send_or_edit молча пропустит
        self.answers: list[tuple] = []

    async def answer(self, text, reply_markup=None, **kwargs) -> None:
        self.answers.append((text, reply_markup))


ADMIN_DB = {"id": 1001, "role": "admin", "is_active": True}


# ----------------------------------------------------------------------
# 1–3. Карточка: главное меню + возврат в исходный список и страницу
# ----------------------------------------------------------------------
async def test_card_has_main_menu_button(task_service, settings_repo, admin_user) -> None:
    """В карточке есть кнопка «🏠 Главное меню» (callback 'menu')."""
    task_id = await _create_task(task_service, settings_repo, admin_user)
    kb = tk.task_card_keyboard(task_id, can_edit=True, can_delete=True,
                               can_change_status=True)
    assert "menu" in callbacks_of(kb)


async def test_card_returns_to_source_list_and_page(task_service, settings_repo,
                                                    admin_user) -> None:
    """«⬅️ К списку» ведёт в тот же фильтр и страницу, из которых открыта карточка."""
    task_id = await _create_task(task_service, settings_repo, admin_user)
    kb = tk.task_card_keyboard(task_id, can_edit=True, can_delete=True,
                               can_change_status=True, return_to="my:2")
    assert "list:my:2" in callbacks_of(kb)            # фильтр «мои», страница 3
    assert "list:all:0" not in callbacks_of(kb)       # без сброса в общий список


async def test_list_context_saved_per_render(task_service, admin_user) -> None:
    """last_list записывается при каждом рендере и перезаписывается."""
    state = make_state()
    await lists_h._render_list(ScreenMessage(), task_service, ADMIN_DB, "UTC",
                               "my", 2, state=state)
    assert (await state.get_data())["last_list"] == "my:2"

    await lists_h._render_list(ScreenMessage(), task_service, ADMIN_DB, "UTC",
                               "all", 0, state=state)
    assert (await state.get_data())["last_list"] == "all:0"  # не осталось от my:2


async def test_card_callback_uses_saved_context(task_service, settings_repo,
                                                admin_user) -> None:
    """cb_task читает last_list из FSM и строит кнопку возврата по нему."""
    task_id = await _create_task(task_service, settings_repo, admin_user)
    state = make_state()
    await state.update_data(last_list="over:1")
    screen = ScreenMessage()
    cb = FakeCallbackQuery(screen, f"task:{task_id}")

    await tm.cb_task(cb, state, task_service, ADMIN_DB, "UTC")

    text, kb = screen.edits[0]
    assert "list:over:1" in callbacks_of(kb)
    assert "menu" in callbacks_of(kb)


async def test_card_fallback_without_context(task_service, settings_repo,
                                             admin_user) -> None:
    """Нет контекста → безопасный возврат в общий список (list:all:0)."""
    task_id = await _create_task(task_service, settings_repo, admin_user)
    kb = tk.task_card_keyboard(task_id, can_edit=True, can_delete=True,
                               can_change_status=True, return_to=None)
    assert "list:all:0" in callbacks_of(kb)

    state = make_state()  # пустые данные — карточка не из списка
    screen = ScreenMessage()
    await tm.cb_task(FakeCallbackQuery(screen, f"task:{task_id}"),
                     state, task_service, ADMIN_DB, "UTC")
    text, kb = screen.edits[0]
    assert "list:all:0" in callbacks_of(kb)


# ----------------------------------------------------------------------
# 4–5. Поиск переживает меню
# ----------------------------------------------------------------------
async def test_menu_keeps_search_and_nav_data(task_service, settings_repo,
                                              admin_user) -> None:
    """cb_menu (leave_scenario) сохраняет search_text и last_list,
    стирая временные данные сценария."""
    await _create_task(task_service, settings_repo, admin_user, "Договор аренды")
    state = make_state()
    await state.set_state(AddTaskStates.title)
    await state.update_data(title="черновик", last_list="all:3", search_text="договор")

    screen = ScreenMessage()
    await start_h.cb_menu(FakeCallbackQuery(screen, "menu"), state, ADMIN_DB)

    data = await state.get_data()
    assert data["search_text"] == "договор"           # поиск жив
    assert data["last_list"] == "all:3"               # контекст списка жив
    assert "title" not in data                        # черновик стёрт
    assert await state.get_state() is None            # сценарий закрыт
    # Уведомление об отмене показано:
    assert any("Незавершенный сценарий отменен" in t for t, _ in screen.answers)


async def test_search_pagination_works_after_menu(task_service, settings_repo,
                                                  admin_user) -> None:
    """Полный цикл: поиск → меню → страница результатов поиска работает."""
    await _create_task(task_service, settings_repo, admin_user, "Договор аренды")
    state = make_state()
    await state.set_state(ValueInputStates.waiting_value)
    await state.update_data(purpose="search")

    msg = InputMessage("договор")
    await lists_h.step_search_text(msg, state, task_service, ADMIN_DB, "UTC")
    assert (await state.get_data())["search_text"] == "договор"

    # Переход в главное меню — состояние очищено, данные поиска сохранены.
    screen = ScreenMessage()
    await start_h.cb_menu(FakeCallbackQuery(screen, "menu"), state, ADMIN_DB)
    assert await state.get_state() is None
    assert (await state.get_data())["search_text"] == "договор"

    # Кнопка страницы поиска (list:srch:0) по-прежнему работает.
    page = ScreenMessage()
    await lists_h.cb_list_page(FakeCallbackQuery(page, "list:srch:0"),
                               task_service, ADMIN_DB, "UTC", state)
    text, _ = page.edits[0]
    assert "Договор аренды" in text


# ----------------------------------------------------------------------
# 6–8. Очистка незавершённого сценария и чистый старт нового
# ----------------------------------------------------------------------
async def test_unfinished_scenario_cleared_by_menu() -> None:
    """cb_menu завершает FSM-сценарий: состояние None, черновик стёрт."""
    state = make_state()
    await state.set_state(AddTaskStates.title)
    await state.update_data(title="Брошенная задача", description="x")

    screen = ScreenMessage()
    await start_h.cb_menu(FakeCallbackQuery(screen, "menu"), state, ADMIN_DB)

    assert await state.get_state() is None
    assert "title" not in await state.get_data()


async def test_next_text_not_captured_after_menu() -> None:
    """После меню у обработчиков сценариев нет активного состояния —
    следующий текст пойдёт обычным обработчикам команд/текста, а не сценарию."""
    state = make_state()
    await state.set_state(AddTaskStates.title)
    await state.update_data(title="Брошенная задача")

    screen = ScreenMessage()
    await start_h.cb_menu(FakeCallbackQuery(screen, "menu"), state, ADMIN_DB)
    # Шаги сценариев зарегистрированы с фильтром состояния (aiogram):
    # при состоянии None ни один из них не получит сообщение.
    assert await state.get_state() is None
    assert "title" not in await state.get_data()


async def test_new_scenario_starts_with_clean_data() -> None:
    """После отмены сценария новый сценарий создания начинается с чистых данных."""
    state = make_state()
    await state.set_state(AddTaskStates.title)
    await state.update_data(title="старый черновик")

    msg = ScreenMessage()
    from app.handlers.tasks import _start_creation  # локальный импорт сценария
    await _start_creation(msg, state)

    assert await state.get_state() == AddTaskStates.title
    data = await state.get_data()
    assert data["title"] is None and data["description"] is None \
        and data["category_id"] is None


# ----------------------------------------------------------------------
# 9. Подменю карточки и история
# ----------------------------------------------------------------------
async def test_submenu_returns_to_card_and_menu() -> None:
    """Все подменю карточки имеют «⬅️ К карточке» и «🏠 Главное меню»."""
    statuses = [{"id": 1, "name": "Новая"}]
    priorities = [{"id": 1, "name": "Обычный"}]
    users = [{"id": 9, "full_name": "Иван"}]
    for markup in (tk.status_choice_keyboard(5, statuses),
                   tk.priority_choice_keyboard(5, priorities),
                   tk.assignee_choice_keyboard(5, users),
                   tk.edit_field_keyboard(5)):
        cbs = callbacks_of(markup)
        assert "task:5" in cbs and "menu" in cbs


async def test_history_returns_to_card_and_menu() -> None:
    """Экран истории задачи: возврат к карточке и в главное меню."""
    screen = ScreenMessage()

    stub_service = type("S", (), {})()
    stub_service.tasks = type("T", (), {})()
    async def fake_get_history(task_id, limit=20):
        return [{
            "action": "created", "old_value": None, "new_value": "Тест",
            "created_at": "2026-11-20T10:00:00+00:00", "user_name": "Admin",
        }]

    stub_service.tasks.get_history = staticmethod(fake_get_history)

    await tm.cb_history(FakeCallbackQuery(screen, "this:7"), stub_service, "UTC")

    text, kb = screen.edits[0]
    cbs = callbacks_of(kb)
    assert "task:7" in cbs and "menu" in cbs


# ----------------------------------------------------------------------
# 10–15. Административные справочники: ошибки и успех
# ----------------------------------------------------------------------
async def test_empty_name_keeps_state_with_cancel_button(settings_repo) -> None:
    """Пустое название: понятная ошибка + кнопка «Отмена», сценарий жив."""
    state = make_state()
    await state.set_state(ValueInputStates.waiting_value)
    await state.update_data(purpose="refadd:cat")

    msg = InputMessage("")
    handled = await admin_h._run_reference_input(msg, state, settings_repo, ADMIN_DB)

    assert handled
    text, markup = msg.answers[-1]
    assert "не может быть пустым" in text and "fsm:cancel" in callbacks_of(markup)
    assert await state.get_state() == ValueInputStates.waiting_value
    assert (await state.get_data())["purpose"] == "refadd:cat"


async def test_duplicate_name_keeps_state_with_cancel_button(settings_repo) -> None:
    """Дубликат: сообщение с кнопкой «Отмена», состояние сохраняется."""
    state = make_state()
    await state.set_state(ValueInputStates.waiting_value)
    await state.update_data(purpose="refadd:cat")

    msg = InputMessage("Проекты")  # существует в seed-справочнике
    handled = await admin_h._run_reference_input(msg, state, settings_repo, ADMIN_DB)

    assert handled
    text, markup = msg.answers[-1]
    assert "уже существует" in text and "fsm:cancel" in callbacks_of(markup)
    assert await state.get_state() == ValueInputStates.waiting_value


async def test_retry_after_duplicate_error(settings_repo) -> None:
    """Повторный ввод после ошибки дубликата проходит успешно."""
    state = make_state()
    await state.set_state(ValueInputStates.waiting_value)
    await state.update_data(purpose="refadd:cat")

    await admin_h._run_reference_input(InputMessage("Проекты"), state,
                                       settings_repo, ADMIN_DB)
    assert await state.get_state() == ValueInputStates.waiting_value  # ещё в сценарии

    ok = await admin_h._run_reference_input(InputMessage("Логистика"), state,
                                            settings_repo, ADMIN_DB)
    assert ok
    assert await state.get_state() is None  # сценарий завершён


async def test_success_returns_to_reference_list(settings_repo) -> None:
    """После успеха — список справочника с админ-навигацией, не главное меню."""
    state = make_state()
    await state.set_state(ValueInputStates.waiting_value)
    await state.update_data(purpose="refadd:cat")

    msg = InputMessage("Логистика")
    await admin_h._run_reference_input(msg, state, settings_repo, ADMIN_DB)

    assert any("Изменения справочника сохранены" in t for t, _ in msg.answers)
    text, markup = msg.answers[-1]
    assert "Категории" in text
    cbs = callbacks_of(markup)
    assert "refadd:cat" in cbs                      # «Добавить элемент» снова доступен
    assert "menu:admin" in cbs                      # возврат в админ-панель
    assert "menu" not in cbs                        # НЕ главное меню

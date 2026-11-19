"""Тесты бизнес-логики задач: создание, списки, фильтры, статусы, история."""

from __future__ import annotations

from datetime import date, timedelta

from app.utils.dates import deadline_to_iso


async def test_create_task(task_service, settings_repo, admin_user) -> None:
    """Задача сохраняется в SQLite с корректными полями."""
    categories = await settings_repo.list_categories(only_active=True)
    priorities = await settings_repo.list_priorities(only_active=True)
    task_id = await task_service.create_task(
        title="Собрать отчёт",
        description="Отчёт по продажам за квартал",
        category_id=categories[0]["id"],
        priority_id=priorities[-1]["id"],
        assigned_to=None,
        due_date_iso=None,
        user_id=admin_user["id"],
        timezone_name="UTC",
    )
    task = await task_service.get_task(task_id)
    assert task["title"] == "Собрать отчёт"
    assert task["description"] == "Отчёт по продажам за квартал"
    assert task["category"] == categories[0]["name"]
    assert task["priority"] == priorities[-1]["name"]
    assert task["status"] == "Новая"  # первый активный статус справочника
    assert task["creator_name"] == "Администратор Тестов"
    assert task["assignee_name"] is None


async def test_list_tasks_order_asc(task_service, settings_repo, admin_user) -> None:
    """/list по умолчанию: от старых к новым (порядок создания)."""
    categories = await settings_repo.list_categories(only_active=True)
    priorities = await settings_repo.list_priorities(only_active=True)
    ids = []
    for title in ("Первая", "Вторая", "Третья"):
        ids.append(await task_service.create_task(
            title=title, description="", category_id=categories[0]["id"],
            priority_id=priorities[0]["id"], assigned_to=None,
            due_date_iso=None, user_id=admin_user["id"], timezone_name="UTC",
        ))
    tasks = await task_service.tasks.list_tasks(order="asc", limit=10, offset=0)
    assert [t["title"] for t in tasks] == ["Первая", "Вторая", "Третья"]


async def test_filter_by_status_and_category(task_service, settings_repo, admin_user) -> None:
    """Фильтрация по статусу и категории возвращает только подходящие."""
    categories = await settings_repo.list_categories(only_active=True)
    priorities = await settings_repo.list_priorities(only_active=True)
    cat_a, cat_b = categories[0], categories[1]
    await task_service.create_task(title="A1", description="", category_id=cat_a["id"],
                                   priority_id=priorities[0]["id"], assigned_to=None,
                                   due_date_iso=None, user_id=admin_user["id"],
                                   timezone_name="UTC")
    task_b = await task_service.create_task(title="B1", description="",
                                            category_id=cat_b["id"],
                                            priority_id=priorities[0]["id"],
                                            assigned_to=None, due_date_iso=None,
                                            user_id=admin_user["id"], timezone_name="UTC")
    filtered = await task_service.tasks.list_tasks(category_id=cat_b["id"], limit=10, offset=0)
    assert [t["title"] for t in filtered] == ["B1"]
    count = await task_service.tasks.list_tasks(category_id=cat_b["id"], count_only=True)
    assert count == 1


async def test_search_text(task_service, settings_repo, admin_user) -> None:
    """Поиск по названию и описанию."""
    categories = await settings_repo.list_categories(only_active=True)
    priorities = await settings_repo.list_priorities(only_active=True)
    cat, prio = categories[0], priorities[0]
    await task_service.create_task(title="Договор аренды", description="",
                                   category_id=cat["id"], priority_id=prio["id"],
                                   assigned_to=None, due_date_iso=None,
                                   user_id=admin_user["id"], timezone_name="UTC")
    await task_service.create_task(title="Инвентаризация", description="проверить договоры",
                                   category_id=cat["id"], priority_id=prio["id"],
                                   assigned_to=None, due_date_iso=None,
                                   user_id=admin_user["id"], timezone_name="UTC")
    found = await task_service.tasks.list_tasks(search_text="договор", limit=10, offset=0)
    assert {t["title"] for t in found} == {"Договор аренды", "Инвентаризация"}


async def test_change_status_sets_completed_at(task_service, settings_repo, admin_user) -> None:
    """Переход в завершающий статус ставит дату завершения; выход из него сбрасывает."""
    task = await task_service.get_task(
        await task_service.create_task(
            title="Задача X", description="", category_id=1,
            priority_id=1, assigned_to=None, due_date_iso=None,
            user_id=admin_user["id"], timezone_name="UTC")
    )
    statuses = await settings_repo.list_statuses(only_active=True)
    done = next(s for s in statuses if s["name"] == "Выполнена")
    updated = await task_service.change_status(task["id"], done["id"], admin_user["id"])
    assert updated["status"] == "Выполнена"
    assert updated["status_is_final"] is True or updated["completed_at"]
    assert updated["completed_at"] is not None

    work = next(s for s in statuses if s["name"] == "В работе")
    reverted = await task_service.change_status(task["id"], work["id"], admin_user["id"])
    assert reverted["completed_at"] is None


async def test_assignee_change_and_history(task_service, users_repo, admin_user,
                                           member_user) -> None:
    """Назначение исполнителя фиксируется в истории изменений."""
    from app.database.repositories.settings import SettingsRepository

    # users_repo уже создал пользователя; нужен доступ к settings — создаём сервис заново не нужен:
    task = await task_service.get_task(
        await task_service.create_task(
            title="Историческая", description="", category_id=1, priority_id=1,
            assigned_to=None, due_date_iso=None, user_id=admin_user["id"],
            timezone_name="UTC")
    )
    updated = await task_service.change_assignee(task["id"], member_user["id"],
                                                 admin_user["id"])
    assert updated["assignee_name"] == member_user["full_name"]

    history = await task_service.tasks.get_history(task["id"])
    actions = {h["action"] for h in history}
    assert "created" in actions and "assignee" in actions
    latest = history[0]  # история от последней записи
    assert latest["action"] == "assignee"
    assert latest["new_value"] == member_user["full_name"]


async def test_edit_fields_updates_history(task_service, admin_user,
                                           member_user) -> None:
    """Редактирование названия и описание попадает в историю."""
    from app.utils.dates import now_utc_iso

    task = await task_service.get_task(
        await task_service.create_task(
            title="Старое название", description="old", category_id=1,
            priority_id=1, assigned_to=None, due_date_iso=None,
            user_id=admin_user["id"], timezone_name="UTC")
    )
    updated = await task_service.edit_fields(
        task["id"], admin_user["id"], title="Новое название", description="new"
    )
    assert updated["title"] == "Новое название"
    assert updated["description"] == "new"

    # Очистка дедлайна (None как намерение, не «не менять»).
    cleared = await task_service.edit_fields(task["id"], admin_user["id"], due_date=None)
    assert cleared["due_date"] is None

    history = await task_service.tasks.get_history(task["id"])
    actions = {h["action"] for h in history}
    assert {"title", "description", "due_date"} <= actions


async def test_pagination(task_service, settings_repo, admin_user) -> None:
    """Пагинация по 10 записей на страницу."""
    categories = await settings_repo.list_categories(only_active=True)
    priorities = await settings_repo.list_priorities(only_active=True)
    cat, prio = categories[0]["id"], priorities[0]["id"]
    for i in range(25):
        await task_service.create_task(title=f"Задача {i:02d}", description="",
                                       category_id=cat, priority_id=prio,
                                       assigned_to=None, due_date_iso=None,
                                       user_id=admin_user["id"], timezone_name="UTC")
    total = await task_service.tasks.list_tasks(count_only=True)
    assert total == 25
    page1 = await task_service.tasks.list_tasks(limit=10, offset=0, order="asc")
    page3 = await task_service.tasks.list_tasks(limit=10, offset=20, order="asc")
    assert len(page1) == 10 and len(page3) == 5


async def test_overdue_filter(task_service, settings_repo, admin_user) -> None:
    """Просроченные: дедлайн в прошлом + незавершённый статус."""
    categories = await settings_repo.list_categories(only_active=True)
    priorities = await settings_repo.list_priorities(only_active=True)
    cat, prio = categories[0]["id"], priorities[0]["id"]
    past = deadline_to_iso(date.today() - timedelta(days=5), "UTC")
    future = deadline_to_iso(date.today() + timedelta(days=5), "UTC")

    await task_service.create_task(title="Просрочка", description="", category_id=cat,
                                   priority_id=prio, assigned_to=None,
                                   due_date_iso=past, user_id=admin_user["id"],
                                   timezone_name="UTC")
    await task_service.create_task(title="Своевременно", description="", category_id=cat,
                                   priority_id=prio, assigned_to=None,
                                   due_date_iso=future, user_id=admin_user["id"],
                                   timezone_name="UTC")
    overdue = await task_service.tasks.list_tasks(only_overdue=True, limit=10, offset=0)
    assert [t["title"] for t in overdue] == ["Просрочка"]

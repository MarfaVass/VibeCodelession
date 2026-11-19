"""Тесты прав доступа: роли ADMIN и MEMBER, сереверные проверки в TaskService."""

from __future__ import annotations

from app.services.task_service import PermissionDenied


async def test_admin_can_do_everything(task_service, admin_user, sample_task) -> None:
    """Администратору разрешены все операции над любой задачей."""
    t = sample_task
    assert task_service.can_view_task(admin_user, t)
    assert task_service.can_edit_task(admin_user, t)
    assert task_service.can_change_status(admin_user, t)
    assert task_service.can_delete_task(admin_user, t)


async def test_member_can_view_but_not_edit_foreign(task_service, member_user,
                                                    sample_task) -> None:
    """Участник видит чужую задачу, но не редактирует и не удаляет её."""
    t = sample_task
    assert task_service.can_view_task(member_user, t) is True
    assert task_service.can_edit_task(member_user, t) is False
    assert task_service.can_change_status(member_user, t) is False
    assert task_service.can_delete_task(member_user, t) is False


async def test_member_can_work_on_own_assigned(task_service, member_user,
                                               admin_user, settings_repo) -> None:
    """Участник меняет статус своей назначенной задачи, пока она не завершена."""
    cat_id = (await settings_repo.list_categories(only_active=True))[0]["id"]
    prio_id = (await settings_repo.list_priorities(only_active=True))[0]["id"]
    task_id = await task_service.create_task(
        title="Для участника", description="", category_id=cat_id,
        priority_id=prio_id, assigned_to=member_user["id"],
        due_date_iso=None, user_id=admin_user["id"], timezone_name="UTC")
    task = await task_service.get_task(task_id)

    assert task_service.can_edit_task(member_user, task) is True
    assert task_service.can_change_status(member_user, task) is True

    # Участник переводит задачу в работу.
    statuses = await settings_repo.list_statuses(only_active=True)
    work = next(s for s in statuses if s["name"] == "В работе")
    updated = await task_service.change_status(task_id, work["id"], member_user["id"])
    assert updated["status"] == "В работе"

    # Участник завершает задачу — разрешено (переход в завершающий).
    done = next(s for s in statuses if s["name"] == "Выполнена")
    updated = await task_service.change_status(task_id, done["id"], member_user["id"])
    assert updated["status"] == "Выполнена"

    # Но выйти из завершающего статуса участник уже не может.
    assert task_service.can_change_status(member_user, updated) is False


async def test_inactive_user_cannot_access(task_service, users_repo, admin_user) -> None:
    """Деактивированный участник теряет полный доступ."""
    await users_repo.ensure_registered(2002, "@blocked", "Заблокированный Тест")
    await users_repo.set_active(2002, False)
    blocked = await users_repo.get(2002)
    assert blocked["is_active"] is False
    # Middleware не пропустит неактивного пользователя, и даже если бы
    # пропустил — права не дают выполнять действия.
    assert task_service.can_delete_task(blocked, {"assigned_to": None}) is False


async def test_assignee_must_be_active(task_service, users_repo, admin_user) -> None:
    """Назначить исполнителя можно только активному участнику."""
    await users_repo.ensure_registered(3001, "@ghost", "Неактивный Исполнитель")
    await users_repo.set_active(3001, False)

    task = await task_service.get_task(
        await task_service.create_task(title="Кто-то", description="", category_id=1,
                                       priority_id=1, assigned_to=None,
                                       due_date_iso=None, user_id=admin_user["id"],
                                       timezone_name="UTC")
    )
    try:
        await task_service.change_assignee(task["id"], 3001, admin_user["id"])
        raised = False
    except PermissionDenied:
        raised = True
    assert raised


async def test_delete_only_admin(task_service, admin_user, member_user,
                                 sample_task) -> None:
    """Удаление задачи: админ может, участник не может."""
    assert await task_service.delete_task(sample_task["id"], admin_user["id"]) is True
    assert await task_service.get_task(sample_task["id"]) is None

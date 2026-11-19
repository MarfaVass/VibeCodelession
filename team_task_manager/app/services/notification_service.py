"""Сервис уведомлений.

Отправляет участникам команды сообщения о событиях с задачами:
  * назначение исполнителя;
  * изменение статуса (уведомляется автор);
  * завершение задачи (уведомляются автор и исполнитель).

Защита от повторной отправки: каждое событие получает уникальный
event_key, который записывается в таблицу notifications. Если ключ
уже есть — событие считалось отправленным и повторно не рассылается.

Ошибки доставки НЕ прерывают основную операцию — только логируются.
Архитектурно расширяемо: метод schedule_deadline_reminder() оставляет
точку для будущих напоминаний о дедлайнах.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot

from ..database.database import Database

logger = logging.getLogger(__name__)

NOTIFY_PREFIX = "notify:"


class NotificationService:
    """Отправка уведомлений с дедупликацией по ключу события."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def _not_sent_yet(self, event_key: str) -> bool:
        """True, если такое событие ещё не отправлялось.

        Если событие новое — сразу резервируем ключ (INSERT OR IGNORE),
        чтобы параллельные обработчики не отправили уведомление дважды.
        """
        cursor = await self.db.conn.execute(
            "INSERT OR IGNORE INTO notifications (event_key, created_at) "
            "VALUES (?, datetime('now'))",
            (event_key,),
        )
        await self.db.conn.commit()
        return cursor.rowcount == 1

    async def send(self, bot: Bot, user_id: int, text: str, event_key: str | None = None) -> bool:
        """Отправляет сообщение пользователю.

        Экземпляр бота передаётся из обработчика (у объектов Message/CallbackQuery
        в aiogram 3 есть свойство .bot).

        :returns: True — сообщение отправлено, False — отправка пропущена/неудачна.
        """
        if event_key and not await self._not_sent_yet(event_key):
            logger.debug("Уведомление %s уже отправлялось — пропуск", event_key)
            return False
        try:
            await bot.send_message(user_id, text)
            logger.info("Уведомление отправлено пользователю id=%s", user_id)
            return True
        except Exception as exc:  # сеть, 403 (бот заблокирован) и т.п.
            logger.warning("Не удалось отправить уведомление id=%s: %s", user_id, exc)
            return False

    # ------------------------------------------------------------------
    # Типовые события
    # ------------------------------------------------------------------
    async def notify_assignment(
        self, bot: Bot, task: dict[str, Any], old_assignee: int | None
    ) -> None:
        """Уведомить исполнителя о назначении задачи."""
        assignee = task.get("assigned_to")
        if not assignee or assignee == old_assignee:
            return
        key = f"{NOTIFY_PREFIX}assign:{task['id']}:{assignee}"
        text = (
            f"🎯 Вам назначена задача #{task['id']}\n"
            f"<b>{task['title']}</b>\n"
            f"Дедлайн: {task.get('due_date') or '—'}"
        )
        await self.send(bot, assignee, text, event_key=key)

    async def notify_status_change(
        self, bot: Bot, task: dict[str, Any], old_status: str, actor_id: int
    ) -> None:
        """Уведомить автора об изменении статуса его задачи."""
        author = task.get("created_by")
        if not author or author == actor_id:
            return  # автор сам изменил статус — уведомлять не нужно
        key = f"{NOTIFY_PREFIX}status:{task['id']}:{old_status}->{task['status']}"
        text = (
            f"📣 Статус задачи #{task['id']} изменён\n"
            f"<b>{task['title']}</b>\n"
            f"{old_status} → {task['status']}"
        )
        await self.send(bot, author, text, event_key=key)

    async def notify_completion(
        self, bot: Bot, task: dict[str, Any], actor_id: int
    ) -> None:
        """Уведомить автора и исполнителя о завершении задачи."""
        recipients = {r for r in (task.get("created_by"), task.get("assigned_to")) if r}
        recipients.discard(actor_id)
        for user_id in recipients:
            key = f"{NOTIFY_PREFIX}done:{task['id']}:{user_id}"
            text = (
                f"✅ Задача #{task['id']} выполнена\n<b>{task['title']}</b>"
            )
            await self.send(bot, user_id, text, event_key=key)

    # ------------------------------------------------------------------
    # Точка расширения: напоминания о дедлайнах
    # ------------------------------------------------------------------
    async def schedule_deadline_reminder(self, task_id: int, days_before: int = 1) -> None:
        """Заглушка-контракт для будущих напоминаний о дедлайнах.

        Напоминание будет генерировать фоновая задача (например aiocron),
        вызывая send() с ключом f'{NOTIFY_PREFIX}deadline:{task_id}:{days_before}',
        что автоматически исключит повторы.
        """
        logger.debug(
            "schedule_deadline_reminder(%s, days_before=%s) — механика пока не включена",
            task_id, days_before,
        )


# ----------------------------------------------------------------------
# Единственный экземпляр сервиса уведомлений создаётся при старте
# приложения через init_notification_service(db) и получается из хендлеров
# через workflow_data диспетчера (см. main.py).
# ----------------------------------------------------------------------


"""Middleware контроля доступа.

Выполняется для КАЖДОГО входящего события и делает две вещи:
  1. Регистрирует пользователя в БД (первый контакт) и отдаёт его
     обработчикам через workflow_data (user_db).
  2. Блокирует неавторизованных пользователей: неактивные/неизвестные
     участники не должны видеть данные команды.

Также проверяет роли для команд администратора (фильтры в хендлерах
используют user_db из данных события).

Важно: проверка прав выполняется на серверной стороне в каждом
обработчике — здесь лишь базовый контроль «вход в систему».
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

logger = logging.getLogger(__name__)


class AccessControlMiddleware(BaseMiddleware):
    """Вешается на весь Router: наполняет событие данными пользователя."""

    def __init__(self, users_repo, admin_ids: frozenset[int]) -> None:
        """
        :param users_repo: UserRepository (нужны доступы к БД).
        :param admin_ids: множество Telegram ID администраторов из ADMIN_IDS.
        """
        self.users_repo = users_repo
        self.admin_ids = admin_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # У любых интересующих нас событий есть .from_user.
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        username = f"@{tg_user.username}" if tg_user.username else None
        user = await self.users_repo.ensure_registered(
            tg_user.id, username, tg_user.full_name
        )

        # Первый вход из ADMIN_IDS повышает роль до admin.
        if tg_user.id in self.admin_ids and user["role"] != "admin":
            await self.users_repo.set_role(tg_user.id, "admin")
            user = await self.users_repo.get(tg_user.id)
            logger.info("Пользователь id=%s назначен администратором (из ADMIN_IDS)", tg_user.id)

        data["user_db"] = user

        # Неактивные участники (деактивированы админом) — не пускаем вовсе.
        if not user["is_active"]:
            logger.warning("Заблокирован доступ неактивного пользователя id=%s", tg_user.id)
            if isinstance(event, (Message, CallbackQuery)):
                message = event if isinstance(event, Message) else event.message
                if message:
                    await message.answer(
                        "⛔ Доступ закрыт. Обратитесь к администратору команды."
                    )
            return None  # обработчик не вызывается

        return await handler(event, data)

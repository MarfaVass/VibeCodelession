"""Точка входа TEAM TASK MANAGER.

Порядок запуска:
  1. Загрузка настроек из .env (проверка обязательных значений).
  2. Настройка логирования (logs/app.log с ротацией).
  3. Подключение к SQLite, миграции, резервная копия при первом запуске.
  4. Сборка бота aiogram 3: роутеры, middleware доступа, workflow-данные.
  5. Запуск polling с повторами при временных сетевых ошибках.

Бот не запустится, если BOT_TOKEN или ADMIN_IDS не заполнены.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.dispatcher.dispatcher import BackoffConfig
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, ErrorEvent

# Корень проекта = каталог, где лежит main.py.
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import load_settings  # noqa: E402
from app.database.database import Database  # noqa: E402
from app.database.migrations import migrate  # noqa: E402
from app.database.repositories.settings import SettingsRepository  # noqa: E402
from app.database.repositories.users import UserRepository  # noqa: E402
from app.middlewares.access_control import AccessControlMiddleware  # noqa: E402
from app.services.backup_service import BackupService  # noqa: E402
from app.services.statistics_service import StatisticsService  # noqa: E402
from app.services.task_service import TaskService  # noqa: E402
from app.utils.logger import setup_logging  # noqa: E402

logger = logging.getLogger(__name__)


def build_dispatcher(db: Database, settings) -> Dispatcher:
    """Собирает диспетчер: сервисы, роутеры, middleware."""
    dp = Dispatcher()

    # --- Сервисы: передаются обработчикам как именованные аргументы ---
    task_service = TaskService(db)
    statistics_service = StatisticsService(db)

    dp.workflow_data.update(
        db=db,
        task_service=task_service,
        statistics_service=statistics_service,
        settings_repo=SettingsRepository(db),
        users_repo=UserRepository(db),
        timezone_name=settings.timezone,
    )
    # Сервис уведомлений импортируется здесь, чтобы не зациклить модули.
    from app.services.notification_service import NotificationService  # noqa: E402
    dp.workflow_data["notification_service"] = NotificationService(db)

    # --- Роутеры (порядок важен: сначала узкие, потом широкие) ---
    from app.handlers import (  # noqa: E402
        admin,
        exports,
        help as help_module,
        lists,
        start,
        statistics,
        task_management,
        tasks,
    )
    dp.include_routers(
        start.router,
        help_module.router,
        tasks.router,          # создание задачи (FSM)
        task_management.router,# карточка/статусы/редактирование
        lists.router,          # списки и фильтры
        statistics.router,
        exports.router,
        admin.router,          # админ-раздел (проверки ролей внутри)
    )

    # --- Контроль доступа на все события ---
    dp.message.middleware(AccessControlMiddleware(UserRepository(db), settings.admin_ids))
    dp.callback_query.middleware(AccessControlMiddleware(UserRepository(db), settings.admin_ids))

    # --- Централизованная обработка исключений ---
    dp.errors.register(_handle_error)
    return dp


async def _handle_error(event: ErrorEvent, db: Database) -> bool:
    """Показывает пользователю понятное сообщение; подробности — в логах."""
    logger.error("Необработанное исключение: %s", event.exception, exc_info=True)
    update = event.update
    chat_target = update.message or (update.callback_query.message if update.callback_query else None)
    if chat_target is not None:
        try:
            await chat_target.answer(
                "⚠️ Произошла ошибка. Она зафиксирована в журнале — "
                "попробуйте повторить действие позже."
            )
        except Exception:  # noqa: S110 — не критично, если не отправилось
            pass
    return True


async def run() -> None:
    """Полный цикл запуска приложения."""
    settings = load_settings(PROJECT_ROOT)

    # --- Проверка обязательных настроек ДО запуска бота ---
    if not settings.bot_token:
        print("⛔ BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен.")
        sys.exit(1)
    if not settings.admin_ids:
        print("⛔ ADMIN_IDS не задан. Укажите в .env Telegram ID администраторов.")
        sys.exit(1)

    setup_logging(PROJECT_ROOT / "logs", settings.log_level)
    logger.info("=" * 60)
    logger.info("Приложение запускается")
    logger.info("Обслуживаемая команда: одна установка бот — одна команда")

    # --- База данных ---
    db = Database(PROJECT_ROOT / settings.database_path)
    await db.connect()
    await migrate(db)

    # --- Резервная копия при первом запуске ---
    backup_service = BackupService(db.db_path, PROJECT_ROOT / "backups")
    if settings.backup_enabled:
        await backup_service.ensure_startup_backup(db.conn)

    # --- Telegram ---
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = build_dispatcher(db, settings)

    logger.info("Подключение к Telegram API...")
    try:
        me = await bot.get_me()
        logger.info("Бот @%s готов принимать сообщения (id=%s)", me.username, me.id)
    except Exception as exc:
        logger.critical("Не удалось подключиться к Telegram: %s", exc)
        await db.close()
        sys.exit(1)

    # --- Публичные команды в меню бота («/» слева от поля ввода).
    # Без set_my_commands список разделов меню пуст (клавиатура бота
    # показывает только те команды, что зарегистрированы в Telegram API);
    # админ-разделы остаются inline-кнопками главного меню.
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Приветствие и главное меню"),
            BotCommand(command="add", description="Создать задачу (пошагово)"),
            BotCommand(command="my", description="Мои назначенные задачи"),
            BotCommand(command="list", description="Все задачи с фильтрами"),
            BotCommand(command="stats", description="Статистика по базе"),
            BotCommand(command="list_csv", description="Экспорт задач в CSV"),
            BotCommand(command="export_excel", description="Экспорт в Excel (3 листа)"),
            BotCommand(command="help", description="Справка"),
        ])
        logger.info("Меню команд бота установлено (%d команд)", 8)
    except Exception as exc:
        logger.warning("Не удалось установить меню команд: %s", exc)  # не критично

    logger.info("Запуск polling")
    try:
        await dp.start_polling(
            bot,
            handle_signals=True,
            polling_timeout=30,
            # Повторы при временных сетевых ошибках: задержка растёт
            # от 5 до 60 секунд и дальше не увеличивается —
            # бесконечные циклы повторов исключены.
            backoff_config=BackoffConfig(min_delay=5.0, max_delay=60.0,
                                         factor=1.6, jitter=0.0),
        )
    finally:
        logger.info("Приложение останавливается")
        await bot.session.close()
        await db.close()
        logger.info("Ресурсы освобождены, работа завершена")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass

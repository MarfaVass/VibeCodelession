"""Точка входа бота и VK-обработчики сообщений.

Запуск: ``python -m bot.main`` (из корня проекта).

Обработчики тонкие: они только достают текст и payload из события VK и
делегируют всю логику ``DialogueManager``. Возвращённые менеджером сообщения
отправляются пользователю.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from vkbottle import Bot
from vkbottle.bot import Message

from . import keyboards
from .config import load_settings
from .manager import DialogueManager
from .ai_client import OllamaClient
from .knowledge.loader import KnowledgeBase
from .storage import BookingDatabase
from .prompts import load_prompt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bot.main")


def build_manager() -> DialogueManager:
    """Собрать менеджер диалогов из настроек.

    Категория клиента определяется только выбором кнопки, поэтому
    классификационный промпт не используется: модель отвечает на вопросы
    по базе знаний (RAG).
    """

    settings = load_settings()
    if not settings.vk_token:
        # Токен не выводим никогда — только факт его отсутствия/некорректности.
        logger.error("VK_TOKEN не задан. Укажите его в файле .env и перезапустите бота.")
        raise SystemExit(1)
    kb = KnowledgeBase()
    manager = DialogueManager(
        db=BookingDatabase(settings.db_path),
        ai=OllamaClient(
            ollama_url=settings.ollama_url,
            model=settings.ollama_model,
            timeout=settings.ai_timeout,
            max_tokens=settings.ai_max_tokens,
            max_answer_len=settings.ai_max_answer_len,
        ),
        kb=kb,
        system_prompt=load_prompt("system"),
    )
    logger.info(
        "База знаний: %d документов (%s)", len(kb), ", ".join(
            f"{cat}: {n}" for cat, n in kb.categories().items()
        )
    )
    return manager


def create_bot(manager: DialogueManager, token: str) -> Bot:
    """Создать Bot и зарегистрировать обработчики."""

    bot = Bot(token=token)

    @bot.on.message()
    async def on_message(message: Message) -> None:
        try:
            payload = message.get_payload_json() if message.payload else None
        except Exception:  # некорректный payload не должен ронять бота
            payload = None
        replies = await manager.handle_message(
            vk_id=message.peer_id,
            text=message.text or "",
            payload=payload,
        )
        for reply in replies:
            try:
                await message.answer(
                    message=reply.text,
                    keyboard=reply.keyboard or keyboards.empty_keyboard(),
                )
            except Exception:  # noqa: BLE001 — сбой VK API не должен ронять цикл
                logger.exception("Не удалось отправить сообщение пользователю")

    return bot


def main() -> None:
    """Запуск поллинга."""

    settings = load_settings()
    if not settings.vk_token:
        logger.error("VK_TOKEN не задан. Заполните .env (см. README) и перезапустите.")
        raise SystemExit(1)
    manager = build_manager()
    bot = create_bot(manager, settings.vk_token)
    logger.info(
        "Бот запущен. Ollama: %s (модель %s)", settings.ollama_url, settings.ollama_model
    )
    try:
        asyncio.run(bot.run_polling())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную.")


if __name__ == "__main__":
    main()
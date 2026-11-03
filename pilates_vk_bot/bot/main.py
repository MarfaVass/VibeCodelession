"""Точка входа бота и VK-обработчики сообщений.

Запуск: ``python -m bot.main`` (из корня проекта).

Обработчики тонкие: они только достают текст и payload из события VK и
делегируют всю логику ``DialogueManager``. Возвращённые менеджером сообщения
отправляются пользователю.

Пока сообщение обрабатывается (RAG-поиск + генерация на CPU занимает
десятки секунд), пользователю показываются:

* штатный индикатор набора ``messages.setActivity(type="typing")`` —
  обновляется каждые :data:`TYPING_REFRESH` секунд, пока идёт обработка;
* если ответ не готов через :data:`AI_NOTE_DELAY` секунд — одно понятное
  сообщение «Подбираю информацию…» (без повторов, если ответ быстрый).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

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

# Задержка до сообщения «Подбираю информацию…» (с). Ответы быстрее порога
# не получают промежуточных сообщений — dialogs не засоряются.
AI_NOTE_DELAY = 4.0
# Период обновления индикатора набора (с). VK держит «печатает…» около
# 5 секунд, поэтому интервал совпадает с этим значением.
TYPING_REFRESH = 5.0

WAITING_NOTE = (
    "Подбираю информацию по вашему вопросу. Это займёт немного времени."
)


async def run_with_wait_note(
    coro: Awaitable[Any],
    send_note: Callable[[], Awaitable[None]],
    note_delay: float = AI_NOTE_DELAY,
) -> Any:
    """Дождаться результата ``coro``; если дольше ``note_delay`` —

    один раз отправить пользователю промежуточное сообщение. Повторных
    уведомлений нет: они отправляются до завершения обработки.
    """

    task = asyncio.create_task(coro)
    done, _ = await asyncio.wait({task}, timeout=note_delay)
    if task in done:
        # быстрый ответ — ничего лишнего пользователю не отправляем
        return task.result()
    await send_note()
    return await task


async def typing_refresher(
    set_activity: Callable[..., Any],
    peer_id: int,
    stop: asyncio.Event,
    interval: float = TYPING_REFRESH,
) -> None:
    """Поддерживать индикатор набора VK, пока ``stop`` не будет выставлен."""

    while not stop.is_set():
        try:
            await set_activity(type="typing", peer_id=peer_id)
        except Exception:  # noqa: BLE001 — сбой индикатора не влияет на диалог
            logger.debug("Не удалось обновить индикатор набора", exc_info=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass  # индикатор скоро «погаснет» — обновим


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
        peer_id = message.peer_id
        started = time.perf_counter()

        stop = asyncio.Event()
        typing_task = asyncio.create_task(
            typing_refresher(bot.api.messages.set_activity, peer_id, stop)
        )
        try:
            replies = await run_with_wait_note(
                manager.handle_message(
                    vk_id=peer_id,
                    text=message.text or "",
                    payload=payload,
                ),
                send_note=lambda: _send_plain(message, WAITING_NOTE),
            )
            for reply in replies:
                try:
                    await message.answer(
                        message=reply.text,
                        keyboard=reply.keyboard or keyboards.empty_keyboard(),
                    )
                except Exception:  # noqa: BLE001 — сбой VK API не должен ронять цикл
                    logger.exception("Не удалось отправить сообщение пользователю")
        finally:
            # индикатор набора выключается после отправки ответа
            stop.set()
            typing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await typing_task
        logger.info(
            "[VK] сообщение от vk_id=%s обработано за %.1f с", peer_id,
            (time.perf_counter() - started),
        )

    return bot


async def _send_plain(message: Message, text: str) -> None:
    """Отправить текст без клавиатуры (для промежуточного сообщения)."""

    try:
        await message.answer(message=text, keyboard=keyboards.empty_keyboard())
    except Exception:  # noqa: BLE001 — промежуточное сообщение не критично
        logger.debug("Не удалось отправить промежуточное сообщение", exc_info=True)


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
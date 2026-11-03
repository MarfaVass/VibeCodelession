"""Взаимодействие с локальным Ollama (упрощённый RAG).

Клиент синхронный (на ``requests``) и вызывается из асинхронного кода через
``asyncio.to_thread``. Все ошибки нормализуются в :class:`AIUnavailable`
с понятной причиной — обработчик сообщений решает, как объяснить это
пользователю, не аварийно завершаясь.

Модель никогда не видит всю базу знаний: вызывающая сторона (диалоговый
менеджер) сначала находит релевантные фрагменты поиском и передаёт их
в ``ask(..., context=...)``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import requests

logger = logging.getLogger(__name__)


class AIFailureReason(StrEnum):
    """Причина, по которой AI-консультант не смог ответить."""

    UNREACHABLE = "unreachable"  # Ollama не отвечает / не запущена
    TIMEOUT = "timeout"  # ответ не получен вовремя
    HTTP_ERROR = "http_error"  # сервер Ollama вернул ошибку
    MODEL_ERROR = "model_error"  # модель отвалилась или ответ некорректен
    EMPTY_ANSWER = "empty_answer"  # модель вернула пустой ответ
    NOT_CONFIGURED = "not_configured"  # URL/модель не заданы


@dataclass(frozen=True)
class AIUnavailable(Exception):
    """Ошибка работы AI-консультанта."""

    reason: AIFailureReason
    detail: str = ""

    def __post_init__(self) -> None:
        super().__init__(self.detail or self.reason.value)


@dataclass(frozen=True)
class AIAnswer:
    """Успешный ответ модели."""

    text: str


class OllamaClient:
    """Клиент чата Ollama.

    Отвечает только за транспорт и нормализацию ошибок. Что спрашивать и что
    показывать пользователю, решает диалоговый менеджер.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "qwen2.5:3b-32k",
        timeout: float = 90.0,
        max_tokens: int = 150,
        max_answer_len: int = 3800,
        keep_alive: int = -1,
    ) -> None:
        self.base_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.max_answer_len = max_answer_len
        # Сколько Ollama держит модель в памяти: -1 — бессрочно (без
        # перезагрузки с диска ~10 с после паузы между вопросами).
        self.keep_alive = keep_alive

    # ------------------------------------------------------------------ #
    #  Публичный асинхронный интерфейс                                   #
    # ------------------------------------------------------------------ #

    async def ask(
        self,
        question: str,
        *,
        system_prompt: str,
        context: str = "",
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> AIAnswer | AIUnavailable:
        """Задать вопрос модели. Никогда не бросает исключений.

        :param question: сообщение пользователя;
        :param system_prompt: системный промпт (загружается из файла);
        :param context: найденные фрагменты базы знаний (RAG).
        """

        try:
            return await asyncio.to_thread(
                self._ask_sync, question, system_prompt, context,
                max_tokens, timeout,
            )
        except AIUnavailable as error:  # уже нормализовано
            return error
        except Exception as error:  # непредвиденное — всё равно не роняем бота
            logger.exception("Неожиданная ошибка при обращении к Ollama")
            return AIUnavailable(reason=AIFailureReason.MODEL_ERROR, detail=str(error))

    # ------------------------------------------------------------------ #
    #  Синхронная внутренность                                           #
    # ------------------------------------------------------------------ #

    def _ask_sync(
        self,
        question: str,
        system_prompt: str,
        context: str,
        max_tokens: int | None,
        timeout: float | None,
    ) -> AIAnswer:
        question = (question or "").strip()
        if not question:
            return AIUnavailable(reason=AIFailureReason.EMPTY_ANSWER,
                                 detail="Пустой вопрос пользователя")
        if not self.base_url or not self.model:
            return AIUnavailable(reason=AIFailureReason.NOT_CONFIGURED,
                                 detail="Не задан адрес Ollama или модель")

        user_content = question
        if context:
            user_content = (
                "Фрагменты базы знаний Академии:\n\n"
                f"{context}\n\n"
                "Вопрос клиента:\n"
                f"{question}"
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.4,
                "num_predict": max_tokens if max_tokens is not None else self.max_tokens,
            },
        }

        started = time.perf_counter()
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout if timeout is not None else self.timeout,
            )
        except requests.exceptions.Timeout as error:
            raise AIUnavailable(
                reason=AIFailureReason.TIMEOUT,
                detail=f"Ollama не ответила вовремя",
            ) from error
        except requests.exceptions.ConnectionError as error:
            raise AIUnavailable(
                reason=AIFailureReason.UNREACHABLE,
                detail=f"Не удалось подключиться к {self.base_url}",
            ) from error
        except requests.exceptions.RequestException as error:
            raise AIUnavailable(
                reason=AIFailureReason.UNREACHABLE,
                detail=str(error),
            ) from error

        if response.status_code != 200:
            raise AIUnavailable(
                reason=AIFailureReason.HTTP_ERROR,
                detail=f"Ollama вернула HTTP {response.status_code}",
            )

        try:
            data = response.json()
        except ValueError as error:
            raise AIUnavailable(
                reason=AIFailureReason.MODEL_ERROR,
                detail="Ответ Ollama не является корректным JSON",
            ) from error

        content: object = ""
        message = data.get("message")
        if isinstance(message, dict):
            content = message.get("content") or ""
        if not isinstance(content, str) or not content.strip():
            # /api/chat может вернуть ошибку модели в поле error
            if "error" in data:
                reason, detail = AIFailureReason.MODEL_ERROR, str(data["error"])[:200]
            elif content and not isinstance(content, str):
                reason, detail = AIFailureReason.MODEL_ERROR, "неожиданный формат ответа модели"
            else:
                reason, detail = AIFailureReason.EMPTY_ANSWER, "пустой ответ модели"
            raise AIUnavailable(reason=reason, detail=detail)

        content = content.strip()
        self._log_timing(started, data)
        return AIAnswer(text=self._trim(content))

    @staticmethod
    def _log_timing(started: float, data: dict[str, Any]) -> None:
        """Понятные временные отметки этапа обращения к Ollama (для диагностики)."""

        total = (time.perf_counter() - started) * 1000
        prompt_tok = data.get("prompt_eval_count")
        prompt_s = data.get("prompt_eval_duration", 0) / 1e9
        gen_tok = data.get("eval_count")
        gen_s = data.get("eval_duration", 0) / 1e9
        speed = gen_tok / gen_s if gen_tok and gen_s else 0.0
        logger.info(
            "[AI rag] %.1f с всего | промпт: %s ткн / %.1f с | генерация: %s ткн / %.1f с (%.1f ткн/с)",
            total / 1000, prompt_tok, prompt_s, gen_tok, gen_s, speed,
        )
    def _trim(self, text: str) -> str:
        """Урезать ответ до безопасной длины сообщения VK."""

        if len(text) <= self.max_answer_len:
            return text
        return text[: self.max_answer_len - 1].rstrip() + "…"


def describe_ai_problem(error: AIUnavailable) -> str:
    """Человекочитаемое объяснение для пользователя."""

    if error.reason == AIFailureReason.TIMEOUT:
        return (
            "AI-консультант сейчас думает дольше отведённого времени и не успел "
            "ответить. Попробуйте задать вопрос ещё раз или оставьте заявку "
            "командой /book — представитель Академии ответит лично."
        )
    return (
        "Сейчас AI-консультант временно не работает, поэтому я не смог "
        "подготовить ответ. Вы можете задать вопрос позже, оставить заявку "
        "командой /book или написать напрямую: novikovsba@mail.ru."
    )


__all__ = [
    "AIAnswer",
    "AIFailureReason",
    "AIUnavailable",
    "OllamaClient",
    "describe_ai_problem",
]
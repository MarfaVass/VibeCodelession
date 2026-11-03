"""Общие фикстуры и подделки для тестов.

Реальный VK-токен не используется вовсе; Ollama заменяется подделками
(FakeAI), кроме отдельного живого теста доступности (test_ollama_live.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Корень проекта — чтобы import bot.* работал без установки пакета
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PROMPTS_DIR = PROJECT_ROOT / "bot" / "prompts"
DOCUMENTS_DIR = PROJECT_ROOT / "bot" / "knowledge" / "documents"

CATEGORY_CODES = ("specialist", "club", "international", "client")


class FakeAI:
    """Подделка OllamaClient: возвращает заранее заданные ответы."""

    def __init__(
        self,
        answer: str = "Ответ по базе знаний Академии.",
        unavailable: bool = False,
        fail_reason: str = "unreachable",
    ) -> None:
        self.answer = answer
        self.unavailable = unavailable
        self.fail_reason = fail_reason
        self.calls: list[dict] = []

    async def ask(self, question: str, **kwargs) -> object:
        self.calls.append({"question": question, **kwargs})
        if self.unavailable:
            from bot.ai_client import AIFailureReason, AIUnavailable

            return AIUnavailable(reason=AIFailureReason(self.fail_reason), detail="fake")
        from bot.ai_client import AIAnswer

        return AIAnswer(text=self.answer)


class ClassificationAI(FakeAI):
    """Подделка классификатора: возвращает заданный код категории."""

    def __init__(self, code: str) -> None:
        super().__init__(answer=code)

    async def ask(self, question: str, **kwargs) -> object:
        self.calls.append(question)
        from bot.ai_client import AIAnswer, AIFailureReason, AIUnavailable

        if self.answer not in (*CATEGORY_CODES, "ambiguous"):
            return AIUnavailable(reason=AIFailureReason.MODEL_ERROR, detail="fake")
        return AIAnswer(text=self.answer)


@pytest.fixture()
def db(tmp_path):
    from bot.storage import BookingDatabase

    return BookingDatabase(tmp_path / "bookings.db")


@pytest.fixture(scope="session")
def kb():
    from bot.knowledge.loader import KnowledgeBase

    return KnowledgeBase()


@pytest.fixture()
def manager_factory(kb, tmp_path):
    """Фабрика менеджеров с настраиваемой подделкой AI и своей БД."""

    from bot import manager as manager_module
    from bot.knowledge.retriever import KeywordRetriever
    from bot.prompts import load_prompt
    from bot.storage import BookingDatabase

    def _factory(ai: FakeAI | None = None) -> manager_module.DialogueManager:
        return manager_module.DialogueManager(
            db=BookingDatabase(tmp_path / "bookings.db"),
            ai=ai or FakeAI(),
            kb=kb,
            system_prompt=load_prompt("system"),
            classify_prompt=load_prompt("classify"),
            retriever=KeywordRetriever(kb),
        )

    return _factory
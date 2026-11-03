"""Живой тест доступности Ollama и модели из .env.

Проверяется отдельно от остальных тестов: если Ollama не запущена,
тест помечается пропуском (а не провалом) — это диагностика окружения.
"""

from __future__ import annotations

import requests

from bot.ai_client import AIAnswer, AIUnavailable, OllamaClient
from bot.config import load_settings
from bot.prompts import load_prompt


def _ollama_alive(url: str) -> bool:
    try:
        response = requests.get(f"{url}/api/tags", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


async def test_ollama_reachable_and_model_listed():
    settings = load_settings()
    if not _ollama_alive(settings.ollama_url):
        _skip_ollama()
    response = requests.get(f"{settings.ollama_url}/api/tags", timeout=5)
    models = [m["name"] for m in response.json().get("models", [])]
    assert settings.ollama_model in models, (
        f"Модель {settings.ollama_model} не установлена; доступно: {models}"
    )


async def test_ollama_model_answers_real_question():
    settings = load_settings()
    if not _ollama_alive(settings.ollama_url):
        _skip_ollama()
    client = OllamaClient(
        ollama_url=settings.ollama_url,
        model=settings.ollama_model,
        timeout=120,
    )
    result = await client.ask(
        "Привет! Скажи одним предложением, что такое Smart Body Academy.",
        system_prompt=load_prompt("system"),
        max_tokens=120,
    )
    if isinstance(result, AIUnavailable):
        _fail_ollama(result.detail)
    assert isinstance(result, AIAnswer)
    assert len(result.text) > 10
    assert len(result.text) <= 3800


def _skip_ollama():
    reason = "Ollama недоступна на localhost:11434 — проверка окружения пропущена"
    import pytest

    pytest.skip(reason)


def _fail_ollama(detail: str):
    import pytest

    pytest.fail(f"Ollama доступна, но модель не ответила: {detail}")
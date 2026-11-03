"""Тесты AI-клиента: транспорт, нормализация ошибок, RAG-контекст.

Ollama подменяется локальным HTTP-сервером (не реальной моделью) —
проверяется поведение клиента. Живая проверка Ollama — отдельный файл
test_ollama_live.py.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bot.ai_client import AIFailureReason, AIUnavailable, OllamaClient

TEST_SYSTEM = "Ты — тестовый ассистент Академии."
TEST_CONTEXT = "[Фрагмент 1] (Док)\nMatwork 1 стоит 40 000 р."

# Общее состояние фейкового сервера
STATE: dict = {"last_body": None, "force": None}


@pytest.fixture(autouse=True)
def reset_server_state():
    STATE["last_body"] = None
    STATE["force"] = None
    yield
    STATE["last_body"] = None
    STATE["force"] = None


class FakeOllamaHandler(BaseHTTPRequestHandler):
    """Простейшая точка /api/chat для проверки клиента."""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        STATE["last_body"] = body
        model = str(body.get("model") or "")

        if self.path != "/api/chat":
            self.send_response(404)
            self.end_headers()
            return
        if STATE["force"] is not None:
            self._json(STATE["force"])
            return
        if model == "broken-model":
            self.send_response(500)
            self.end_headers()
            return
        if model == "empty-model":
            self._json({"message": {"role": "assistant", "content": ""}})
            return
        if model == "error-model":
            self._json({"error": "model failed"})
            return
        self._json({"message": {"role": "assistant", "content": " Ответ из теста. "}})

    def _json(self, data: dict) -> None:
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args) -> None:  # тишина в логах тестов
        pass


@pytest.fixture(scope="module")
def server_url():
    server = HTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _client(url: str, **kwargs) -> OllamaClient:
    kwargs.setdefault("model", "test-model")
    return OllamaClient(ollama_url=url, timeout=5, **kwargs)


async def test_successful_answer(server_url):
    result = await _client(server_url).ask("вопрос про Matwork 1", system_prompt=TEST_SYSTEM)
    assert result.text == "Ответ из теста."


async def test_system_prompt_sent_alongside_question(server_url):
    await _client(server_url).ask("вопрос", system_prompt=TEST_SYSTEM)
    messages = STATE["last_body"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == TEST_SYSTEM
    assert messages[1]["content"] == "вопрос"


async def test_keep_alive_and_token_limit_sent_to_ollama(server_url):
    """Модель должна оставаться в памяти (keep_alive=-1) и не превышать лимит токенов."""

    client = _client(server_url, model="test-model")  # max_tokens по умолчанию
    await client.ask("вопрос", system_prompt=TEST_SYSTEM)
    body = STATE["last_body"]
    assert body["keep_alive"] == -1
    assert body["options"]["num_predict"] == client.max_tokens

    await client.ask("вопрос", system_prompt=TEST_SYSTEM, max_tokens=42)
    assert STATE["last_body"]["options"]["num_predict"] == 42


async def test_context_is_wrapped_into_prompt(server_url):
    await _client(server_url).ask(
        "сколько стоит Matwork 1?", system_prompt=TEST_SYSTEM, context=TEST_CONTEXT
    )
    content = STATE["last_body"]["messages"][1]["content"]
    assert content.count("Фрагменты базы знаний") == 1
    assert "40 000" in content
    assert "сколько стоит Matwork 1?" in content


async def test_http_error_normalized(server_url):
    result = await _client(server_url, model="broken-model").ask("?", system_prompt=TEST_SYSTEM)
    assert isinstance(result, AIUnavailable)
    assert result.reason == AIFailureReason.HTTP_ERROR


async def test_empty_answer_normalized(server_url):
    result = await _client(server_url, model="empty-model").ask("?", system_prompt=TEST_SYSTEM)
    assert isinstance(result, AIUnavailable)
    assert result.reason == AIFailureReason.EMPTY_ANSWER


async def test_model_error_normalized(server_url):
    result = await _client(server_url, model="error-model").ask("?", system_prompt=TEST_SYSTEM)
    assert isinstance(result, AIUnavailable)
    assert result.reason == AIFailureReason.MODEL_ERROR


async def test_unreachable_url():
    client = _client("http://127.0.0.1:1", model="x")
    result = await client.ask("?", system_prompt=TEST_SYSTEM)
    assert isinstance(result, AIUnavailable)
    assert result.reason == AIFailureReason.UNREACHABLE


async def test_empty_question_not_sent(server_url):
    result = await _client(server_url).ask("   ", system_prompt=TEST_SYSTEM)
    assert isinstance(result, AIUnavailable)
    assert result.reason == AIFailureReason.EMPTY_ANSWER
    assert STATE["last_body"] is None


async def test_long_answer_trimmed_to_vk_limit(server_url):
    STATE["force"] = {"message": {"role": "assistant", "content": "А" * 5000}}
    result = await _client(server_url, max_answer_len=100).ask("?", system_prompt=TEST_SYSTEM)
    assert len(result.text) == 100
    assert result.text.endswith("…")


async def test_garbage_json_normalized(server_url):
    STATE["force"] = {"message": {"role": "assistant", "content": {"strange": "dict"}}}
    result = await _client(server_url).ask("?", system_prompt=TEST_SYSTEM)
    assert isinstance(result, AIUnavailable)
    assert result.reason == AIFailureReason.MODEL_ERROR


async def test_classify_mode_removed_from_api(server_url):
    """Режим classify удалён после отказа от авто-классификации."""
    client = _client(server_url)
    with pytest.raises(TypeError):
        client.ask("?", system_prompt=TEST_SYSTEM, classify=True)  # type: ignore[call-arg]
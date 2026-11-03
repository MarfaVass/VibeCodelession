"""Проверки системного промпта.

Промпт влияет на скорость (prompt_eval на CPU) и достоверность, поэтому
ключевые правила закреплены тестами: компактность и запрет «выдумывания».
"""

from __future__ import annotations

from pathlib import Path

from bot.prompts import load_prompt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT = load_prompt("system")


def test_system_prompt_is_compact() -> None:
    """Каждая тысяча символов промпта — секунды prompt_eval на CPU."""

    raw = (PROJECT_ROOT / "bot" / "prompts" / "system.txt").read_text(encoding="utf-8")
    assert len(raw) <= 1200, f"системный промпт разросся: {len(raw)} символов"


def test_system_prompt_keeps_key_rules() -> None:
    lowered = SYSTEM_PROMPT.lower()
    for required in ("только факты", "не придумывай", "/book", "медицинских", "предварительн"):
        assert required in lowered, f"из промпта исчезло правило: {required}"
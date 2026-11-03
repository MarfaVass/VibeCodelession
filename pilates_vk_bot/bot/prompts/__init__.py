"""Загрузка системных промптов из текстовых файлов.

Промпты лежат в ``bot/prompts/*.txt`` и редактируются без изменения кода.
"""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    """Загрузить промпт по имени файла без расширения (например, ``system``)."""

    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Промпт не найден: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Промпт пуст: {path}")
    return text


__all__ = ["load_prompt"]
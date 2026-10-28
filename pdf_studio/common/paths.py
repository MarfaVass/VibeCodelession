"""Пути проекта PDF Studio.

Все каталоги определяются относительно расположения этого модуля
(pdf_studio/common/), поэтому запуск возможен из любой текущей
папки терминала.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  # каталог pdf_studio/
DATA_DIR = BASE_DIR / "data"
TEMPLATE_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
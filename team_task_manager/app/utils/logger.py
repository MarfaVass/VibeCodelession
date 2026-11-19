"""Централизованное логирование.

Логи пишутся одновременно:
  * в файл logs/app.log — с ротацией по размеру (5 МБ, до 5 старых файлов);
  * в консоль (stdout) — только форматированная строка без деталей.

В логи запрещено записывать токены и другие секреты — поэтому
в main.py logging отключает шумные логи aiogram, а в сообщениях
об ошибках токен маскируется.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_FILE_SIZE = 5 * 1024 * 1024  # 5 МБ
LOG_BACKUP_COUNT = 5             # сколько старых файлов хранить


def setup_logging(logs_dir: Path, level: str = "INFO") -> None:
    """Один раз настраивает корневой логгер приложения.

    :param logs_dir: каталог для файла app.log (создаётся при необходимости).
    :param level: строка уровня: DEBUG, INFO, WARNING, ERROR, CRITICAL.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Сбрасываем старые обработчики, чтобы setup_logging можно было
    # безопасно вызвать повторно (например, в тестах).
    root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=LOG_FILE_SIZE, backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # aiogram и aiohttp пишут очень подробные DEBUG-логи — приглушаем их,
    # чтобы файл не раздувался (уровень не ниже INFO, как бы ни просил DEBUG).
    logging.getLogger("aiogram.event").setLevel(logging.INFO)
    logging.getLogger("aiogram.client.session").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Логирование настроено (уровень %s)", level)

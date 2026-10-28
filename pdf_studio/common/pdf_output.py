"""Единый механизм создания и открытия PDF для всех сценариев PDF Studio.

render_and_save() заполняет HTML-шаблон Jinja2, сохраняет PDF в
pdf_studio/output/ с уникальным именем и возвращает путь к файлу.
Уникальность обеспечивается меткой времени в имени, поэтому ранее
созданные документы никогда не перезаписываются.

Логика рендера и открытия скопирована из работающего
pdf_checkmaker/pdf_generator.py, чтобы сохранить проверенное поведение.
"""

from datetime import datetime
from pathlib import Path

from common.errors import DataError
from common.paths import OUTPUT_DIR, TEMPLATE_DIR


def unique_output_path(base_name: str) -> Path:
    """Свободное имя вида certificate_2026-10-28_14-32-07.pdf (без перезаписи)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source = Path(base_name)
    stem = source.stem
    suffix = source.suffix or ".pdf"
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    candidate = OUTPUT_DIR / f"{stem}_{stamp}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = OUTPUT_DIR / f"{stem}_{stamp}-{counter}{suffix}"
        counter += 1
    return candidate


def render_and_save(template_name: str, context: dict, output_base: str) -> Path:
    """Заполняет template_name контекстом и сохраняет PDF, возвращая путь."""
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError:
        raise DataError(
            "Не установлена библиотека Jinja2. Установите зависимости:\n"
            "pip install -r pdf_checkmaker/requirements.txt"
        )
    try:
        from weasyprint import HTML
    except ImportError:
        raise DataError(
            "Не установлена библиотека WeasyPrint. Установите зависимости:\n"
            "pip install -r pdf_checkmaker/requirements.txt\n"
            "(для Windows также требуются GTK/Pango — см. README.md)."
        )

    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = environment.get_template(template_name)
    html = template.render(**context)

    output_path = unique_output_path(output_base)
    HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf(output_path)
    return output_path


def open_pdf(path: Path) -> None:
    """Открывает PDF стандартной программой просмотра документов Windows."""
    import os

    if not hasattr(os, "startfile"):
        return  # Не Windows — автоматическое открытие недоступно.
    try:
        path = Path(path)
        # noqa: S606 — намеренное открытие только что созданного отчета
        os.startfile(str(path))
        print(f"PDF открыт в стандартной программе просмотра: {path}")
    except OSError as error:
        print(f"Не удалось открыть PDF автоматически: {error}")
        print(f"Откройте файл вручную: {path}")
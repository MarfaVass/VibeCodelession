"""PDF Studio — главное окно выбора сценария.

Приложение строится на том же механизме, что и pdf_checkmaker:
Jinja2-шаблон → WeasyPrint → PDF → автооткрытие. Реализованы все три
сценария: сертификат (этап 1), отчет о продажах (этап 2) и
коммерческое предложение по каталогу (этап 3).

Запуск (PowerShell, из корня репозитория):
    .\\venv\\Scripts\\python.exe pdf_studio\\app.py
"""

import sys
from pathlib import Path

# Гарантируем импорт sibling-пакетов независимо от текущей папки запуска.
_STUDIO_DIR = Path(__file__).resolve().parent
if str(_STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(_STUDIO_DIR))

import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402

from gui.sales_frame import SalesWindow  # noqa: E402
from gui.certificate_frame import CertificateWindow  # noqa: E402
from gui.quotation_frame import QuotationWindow  # noqa: E402

SCENARIOS = (
    ("sales", "Отчет о продажах",
     "Реализовано (этап 2): отчет по CSV с выбором включаемых разделов"),
    ("certificate", "Создать сертификат",
     "Персональный PDF-сертификат по полям формы"),
    ("quote", "Коммерческое предложение",
     "Реализовано (этап 3): предложение по позициям каталога CSV"),
)


class PdfStudioApp(tk.Tk):
    """Главное окно: выбор одного из трех сценариев."""

    def __init__(self):
        super().__init__()
        self.title("PDF Studio — генератор деловых PDF-документов")
        self.resizable(False, False)

        header = ttk.Label(
            self, text="Выберите тип документа",
            font=("TkDefaultFont", 14, "bold"),
        )
        header.pack(anchor="w", padx=22, pady=(18, 4))

        stage = ttk.Label(
            self, foreground="#666",
            text="Этапы 0–3: все три сценария реализованы. "
                 "Результаты сохраняются в pdf_studio\\output\\.",
        )
        stage.pack(anchor="w", padx=22, pady=(0, 12))

        for key, name, note in SCENARIOS:
            row = ttk.Frame(self)
            row.pack(fill="x", padx=22, pady=7)
            buttons = ttk.Button(
                row, text=name, width=26, command=lambda k=key: self._open(k)
            )
            buttons.pack(side="left", ipady=6)
            ttk.Label(row, foreground="#777", text=note).pack(
                side="left", padx=14
            )

        ttk.Label(
            self, foreground="#888", font=("TkDefaultFont", 8),
            text="PDF создается в pdf_studio\\output\\ и автоматически "
                 "открывается в программе просмотра документов.",
        ).pack(anchor="w", padx=22, pady=(10, 16))

    def _open(self, key: str) -> None:
        if key == "certificate":
            CertificateWindow(self)
        elif key == "sales":
            SalesWindow(self)
        elif key == "quote":
            QuotationWindow(self)


def main() -> None:
    PdfStudioApp().mainloop()


if __name__ == "__main__":
    main()
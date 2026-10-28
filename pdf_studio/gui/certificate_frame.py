"""Окно «Создать сертификат» — форма полей и кнопка генерации PDF."""

import sys
from pathlib import Path

# Гарантируем импорт sibling-пакетов независимо от текущей папки запуска.
_STUDIO_DIR = Path(__file__).resolve().parents[1]
if str(_STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(_STUDIO_DIR))

from datetime import date  # noqa: E402

import tkinter as tk  # noqa: E402
from tkinter import messagebox, ttk  # noqa: E402

from common import pdf_output  # noqa: E402
from common.errors import DataError  # noqa: E402
from documents import certificate  # noqa: E402
from gui.tk_helpers import enable_entry_shortcuts  # noqa: E402

# Демонстрационное заполнение (кнопка «Пример») — шуточная номинация,
# не заявляющая никакой официальной квалификации.
DEMO_FILL: dict[str, str] = {
    "recipient": "Анна Смирнова",
    "occasion": "Клавиатурный подвиг: проект сдан без единой правки шаблона",
    "date": date.today().strftime("%d.%m.%Y"),
    "org": "Курс вайб-кодирования",
    "number": "",
}

FIELDS = (
    ("recipient", "Имя получателя", True,
     "Например: Анна Смирнова"),
    ("occasion", "Курс, мероприятие или номинация", True,
     "Например: Клавиатурный подвиг — шуточная номинация"),
    ("date", "Дата (ДД.ММ.ГГГГ)", False,
     "По умолчанию — сегодняшняя"),
    ("org", "Организация или автор", False,
     "Пусто — подставится значение по умолчанию"),
    ("number", "Номер сертификата", False,
     "Пусто — номер сгенерируется автоматически"),
)


class CertificateWindow(tk.Toplevel):
    """Форма сертификата: поля, пример заполнения, генерация PDF."""

    def __init__(self, master):
        super().__init__(master)
        self.title("PDF Studio — Создать сертификат")
        self.resizable(False, False)
        self.vars: dict[str, tk.StringVar] = {}

        header = ttk.Label(
            self, text="Персональный сертификат",
            font=("TkDefaultFont", 13, "bold"),
        )
        hint = ttk.Label(
            self, foreground="#666",
            text="Обязательные поля отмечены звездочкой. "
                 "Сертификат носит поздравительный характер.",
        )
        header.pack(anchor="w", padx=16, pady=(14, 2))
        hint.pack(anchor="w", padx=16, pady=(0, 10))

        form = ttk.Frame(self)
        form.pack(padx=16, pady=(0, 8))
        for row, (key, label, required, note) in enumerate(FIELDS):
            ttk.Label(
                form, text=label + (" *" if required else "")
            ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            var = tk.StringVar(value="")
            self.vars[key] = var
            entry = ttk.Entry(form, width=46, textvariable=var)
            entry.grid(
                row=row, column=1, sticky="we", pady=4
            )
            ttk.Label(form, foreground="#888", text=note).grid(
                row=row, column=2, sticky="w", padx=(8, 0), pady=4
            )

        # Значения по умолчанию: сегодняшняя дата; организация — как в документе.
        self.vars["org"].set(certificate.DEFAULT_ORG)
        self.vars["date"].set(date.today().strftime("%d.%m.%Y"))

        buttons = ttk.Frame(self)
        buttons.pack(padx=16, pady=(2, 6))
        self.create_btn = ttk.Button(
            buttons, text="Создать PDF", command=self._create_pdf
        )
        ttk.Button(
            buttons, text="Заполнить пример", command=self._fill_demo
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            buttons, text="Сгенерировать номер",
            command=self._generate_number
        ).pack(side="left", padx=(0, 6))
        self.create_btn.pack(side="left")

        self.status = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self.status, foreground="#1c6b32",
            wraplength=520, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # Ctrl+V / Ctrl+C / Ctrl+X / Ctrl+A во всех полях, включая русскую раскладку.
        enable_entry_shortcuts(self)

    def _fill_demo(self) -> None:
        """Заполняет форму демонстрационными данными для показа приложения."""
        for key, value in DEMO_FILL.items():
            self.vars[key].set(value)

    def _generate_number(self) -> None:
        """Вставляет номер с сегодняшней датой прямо в поле формы."""
        self.vars["number"].set(
            certificate.generate_certificate_number(date.today())
        )

    def _create_pdf(self) -> None:
        """Собирает данные формы и создает PDF (валидация — в documents)."""
        data = {key: var.get() for key, var in self.vars.items()}
        self.create_btn.config(state="disabled")
        self.config(cursor="wait")
        try:
            output_path = certificate.create_certificate_pdf(data)
        except DataError as error:
            messagebox.showerror("PDF Studio — ошибка", str(error), parent=self)
            return
        finally:
            self.config(cursor="")
            self.create_btn.config(state="normal")
        pdf_output.open_pdf(output_path)
        self.status.set(f"PDF создан: {output_path}")
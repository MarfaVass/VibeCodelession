"""Окно «Отчет о продажах» — выбор CSV, флажки разделов, генерация PDF."""

import sys
from pathlib import Path

# Гарантируем импорт sibling-пакетов независимо от текущей папки запуска.
_STUDIO_DIR = Path(__file__).resolve().parents[1]
if str(_STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(_STUDIO_DIR))

from decimal import Decimal  # noqa: E402

import tkinter as tk  # noqa: E402
from tkinter import filedialog, messagebox, ttk  # noqa: E402

from common import pdf_output  # noqa: E402
from common.errors import DataError  # noqa: E402
from common.numfmt import format_qty  # noqa: E402
from common.paths import DATA_DIR  # noqa: E402
from documents import sales_report  # noqa: E402
from gui.tk_helpers import enable_entry_shortcuts  # noqa: E402


class SalesWindow(tk.Toplevel):
    """Окно отчета о продажах: загрузка CSV и выбор состава отчета."""

    def __init__(self, master):
        super().__init__(master)
        self.title("PDF Studio — Отчет о продажах")
        self.sales: dict | None = None
        # True, когда пользователь сам выбрал файл через диалог:
        # демо-загрузка тогда не подменяет файл незаметно.
        self._user_file_loaded = False

        header = ttk.Label(
            self, text="Отчет о продажах",
            font=("TkDefaultFont", 13, "bold"),
        )
        hint = ttk.Label(
            self, foreground="#666",
            text="Выручка = цена × количество. Прибыль, маржа и динамика "
                 "не рассчитываются: этих колонок нет в файле.",
            wraplength=540, justify="left",
        )
        header.pack(anchor="w", padx=16, pady=(14, 2))
        hint.pack(anchor="w", padx=16, pady=(0, 10))

        file_row = ttk.Frame(self)
        file_row.pack(fill="x", padx=16, pady=(0, 4))
        ttk.Button(
            file_row, text="Выбрать CSV…", command=self._choose_file
        ).pack(side="left")
        ttk.Button(
            file_row, text="Загрузить демо-файл", command=self._load_demo
        ).pack(side="left", padx=(6, 0))
        self.path_var = tk.StringVar(value=str(DATA_DIR / "sales.csv"))
        ttk.Label(
            file_row, textvariable=self.path_var, foreground="#333"
        ).pack(side="left", fill="x", expand=True, padx=8)

        self.stats = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self.stats, foreground="#1c6b32",
            wraplength=540, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        self.option_vars: dict[str, tk.BooleanVar] = {}
        options_frame = ttk.Frame(self)
        options_frame.pack(anchor="w", padx=16, pady=(0, 6))
        options_frame.columnconfigure(0, weight=1)
        ttk.Label(
            options_frame, text="Состав отчета:", font=("TkDefaultFont", 10, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        for index, option in enumerate(sales_report.OPTIONS, start=1):
            var = tk.BooleanVar(value=True)
            self.option_vars[option] = var
            ttk.Checkbutton(
                options_frame, variable=var, text=sales_report.OPTION_LABELS[option]
            ).grid(row=index, column=0, columnspan=2, sticky="w", pady=1)

        presets = ttk.Frame(self)
        presets.pack(anchor="w", padx=16, pady=(4, 2))
        ttk.Button(
            presets, text="Выбрать все", width=16, command=self._select_all
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            presets, text="Минимальный отчет", width=19,
            command=self._select_minimal,
        ).pack(side="left")

        buttons = ttk.Frame(self)
        buttons.pack(anchor="w", padx=16, pady=(8, 4))
        self.create_btn = ttk.Button(
            buttons, text="Сформировать PDF", command=self._create_pdf
        )
        self.create_btn.pack(side="left")

        self.status = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self.status, foreground="#1c6b32",
            wraplength=540, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # Ctrl+V / Ctrl+C / Ctrl+X / Ctrl+A во всех полях, включая русскую раскладку.
        enable_entry_shortcuts(self)

        # Демо-файл загружается сразу, чтобы окно открылось с готовым примером.
        if Path(self.path_var.get()).is_file():
            self._load_file(quiet=True)

    def _choose_file(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Выберите CSV-файл с продажами",
            filetypes=[("CSV-файлы", "*.csv"), ("Все файлы", "*.*")],
            initialdir=str(DATA_DIR),
        )
        if not chosen:
            return
        self._user_file_loaded = True
        self.path_var.set(chosen)
        self._load_file()

    def _load_demo(self) -> None:
        """Загружает демонстрационный sales.csv.

        Если пользователь ранее выбрал свой файл — спрашивает подтверждение:
        файл не подменяется незаметно.
        """
        demo_path = DATA_DIR / "sales.csv"
        if not demo_path.is_file():
            messagebox.showerror(
                "PDF Studio",
                f"Демонстрационный файл не найден: {demo_path}",
                parent=self,
            )
            return
        current = self.path_var.get()
        if self._user_file_loaded and Path(current) != demo_path:
            confirmed = messagebox.askyesno(
                "PDF Studio",
                "Заменить выбранный вами файл демонстрационным?\n"
                f"Текущий файл: {current}",
                parent=self,
            )
            if not confirmed:
                return
        self.path_var.set(str(demo_path))
        self._load_file()

    def _load_file(self, *, quiet: bool = False) -> None:
        """Читает выбранный CSV; ошибки показывает сообщением или в статусе."""
        try:
            self.sales = sales_report.load_sales(self.path_var.get())
        except DataError as error:
            self.sales = None
            self.stats.set("Файл не загружен.")
            if quiet:
                self.status.set(f"{error}")
            else:
                messagebox.showerror(
                    "PDF Studio — ошибка чтения CSV", str(error), parent=self
                )
            return
        total_qty = sum(
            (item["qty"] for item in self.sales["items"]), Decimal("0")
        )
        text = (f"Прочитано товаров: {len(self.sales['items'])}. "
                f"Всего единиц: {format_qty(total_qty)}.")
        if self.sales["skipped"]:
            text += f" Пропущено некорректных строк: {len(self.sales['skipped'])}."
        self.stats.set(text)

    def _select_all(self) -> None:
        for var in self.option_vars.values():
            var.set(True)

    def _select_minimal(self) -> None:
        """Минимальный отчет: основные показатели и таблица товаров."""
        for option, var in self.option_vars.items():
            var.set(option in sales_report.MINIMAL_REPORT_OPTIONS)

    def _create_pdf(self) -> None:
        if self.sales is None:
            messagebox.showwarning(
                "PDF Studio", "Сначала выберите CSV-файл с продажами.",
                parent=self,
            )
            return
        selected = {
            option: var.get() for option, var in self.option_vars.items()
        }
        if not any(selected.values()):
            messagebox.showwarning(
                "PDF Studio",
                "Не выбран ни один раздел отчета.\n"
                "Отметьте хотя бы один чекбокс или нажмите «Выбрать все».",
                parent=self,
            )
            return

        self.create_btn.config(state="disabled")
        self.config(cursor="wait")
        try:
            output_path = sales_report.create_sales_pdf(self.sales, selected)
        except DataError as error:
            messagebox.showerror("PDF Studio — ошибка", str(error), parent=self)
            return
        finally:
            self.config(cursor="")
            self.create_btn.config(state="normal")
        pdf_output.open_pdf(output_path)
        self.status.set(f"PDF создан: {output_path}")
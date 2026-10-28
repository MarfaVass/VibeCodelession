"""Окно «Коммерческое предложение» — каталог, выбор позиций, скидка, PDF."""

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
from common.numfmt import format_money  # noqa: E402
from common.paths import DATA_DIR  # noqa: E402
from documents import quotation  # noqa: E402
from gui.tk_helpers import enable_entry_shortcuts  # noqa: E402

DEMO_DETAILS: dict[str, str] = {
    "supplier": "ООО «Уютный дом» (условные данные)",
    "recipient": "ИП Иванов И.И.",
    "valid_until": "14 дней с даты предложения",
    "comment": "Демонстрационное предложение; товары и цены — примеры каталога.",
}

DETAIL_FIELDS = (
    ("supplier", "Поставщик (необязательно)"),
    ("recipient", "Получатель предложения (необязательно)"),
    ("number", "Номер предложения"),
    ("valid_until", "Срок действия (необязательно)"),
)


class QuotationWindow(tk.Toplevel):
    """Окно коммерческого предложения: каталог → выбор → скидка → PDF."""

    def __init__(self, master):
        super().__init__(master)
        self.title("PDF Studio — Коммерческое предложение")
        self.catalogue: dict | None = None
        self.cart: list[dict] = []  # [{"sku", "qty"}]

        header = ttk.Label(
            self, text="Коммерческое предложение",
            font=("TkDefaultFont", 13, "bold"),
        )
        hint = ttk.Label(
            self, foreground="#666",
            text="Выберите позицию в каталоге и нажмите «Добавить выбранные». "
                 "Скидка применяется только после явного ввода процента.",
            wraplength=560, justify="left",
        )
        header.pack(anchor="w", padx=16, pady=(14, 2))
        hint.pack(anchor="w", padx=16, pady=(0, 8))

        self._build_catalogue_section()
        self._build_cart_section()
        self._build_details_section()
        self._build_actions()

        # Демонстрационный каталог загружается сразу, если он есть.
        default_path = DATA_DIR / "catalogue.csv"
        self.path_var.set(str(default_path))
        if default_path.is_file():
            self._load_file(quiet=False)

        # Ctrl+V / Ctrl+C / Ctrl+X / Ctrl+A во всех полях, включая русскую раскладку.
        enable_entry_shortcuts(self)

    # ─── Загрузка каталога ────────────────────────────────────────────

    def _build_catalogue_section(self) -> None:
        file_row = ttk.Frame(self)
        file_row.pack(fill="x", padx=16, pady=(0, 4))
        ttk.Button(
            file_row, text="Выбрать каталог CSV…", command=self._choose_file
        ).pack(side="left")
        self.path_var = tk.StringVar(value="")
        ttk.Label(
            file_row, textvariable=self.path_var, foreground="#333"
        ).pack(side="left", fill="x", expand=True, padx=8)

        self.stats = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self.stats, foreground="#1c6b32",
            wraplength=560, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 6))

        filter_row = ttk.Frame(self)
        filter_row.pack(fill="x", padx=16, pady=(0, 4))
        self.category_var = tk.StringVar(value=quotation.ALL_CATEGORIES)
        self.category_box = ttk.Combobox(
            filter_row, textvariable=self.category_var, width=22, state="readonly"
        )
        self.category_box.bind(
            "<<ComboboxSelected>>", lambda event: self.apply_filters()
        )
        ttk.Label(filter_row, text="Категория:").pack(side="left")
        self.category_box.pack(side="left", padx=(4, 10))
        ttk.Label(filter_row, text="Поиск (артикул/название):").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_filters())
        ttk.Entry(
            filter_row, textvariable=self.search_var, width=20
        ).pack(side="left", padx=4)
        self.found_var = tk.StringVar(value="")
        ttk.Label(filter_row, textvariable=self.found_var).pack(
            side="left", padx=10
        )

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="x", padx=16, pady=(0, 6))
        self.tree = ttk.Treeview(
            tree_frame, columns=("sku", "name", "category", "price"),
            show="headings", height=7, selectmode="extended",
        )
        for column, heading, width in (
            ("sku", "Артикул", 70), ("name", "Наименование", 250),
            ("category", "Категория", 130), ("price", "Цена, ₽", 70),
        ):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor="w")
        tree_scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="x", expand=True)
        tree_scroll.pack(side="left", fill="y")
        ttk.Button(
            tree_frame, text="Добавить выбранные →",
            command=self._add_selected,
        ).pack(side="left", anchor="n", padx=(6, 0))

    # ─── Состав предложения ───────────────────────────────────────────

    def _build_cart_section(self) -> None:
        ttk.Label(self, text="Состав предложения:", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", padx=16, pady=(2, 2))
        cart_frame = ttk.Frame(self)
        cart_frame.pack(fill="x", padx=16, pady=(0, 4))
        self.cart_tree = ttk.Treeview(
            cart_frame, columns=("sku", "name", "qty", "price", "sum"),
            show="headings", height=4, selectmode="extended",
        )
        for column, heading, width in (
            ("sku", "Артикул", 70), ("name", "Наименование", 240),
            ("qty", "Кол-во", 50), ("price", "Цена, ₽", 70),
            ("sum", "Сумма, ₽", 80),
        ):
            self.cart_tree.heading(column, text=heading)
            self.cart_tree.column(column, width=width, anchor="w")
        cart_scroll = ttk.Scrollbar(
            cart_frame, orient="vertical", command=self.cart_tree.yview
        )
        self.cart_tree.configure(yscrollcommand=cart_scroll.set)
        self.cart_tree.pack(side="left", fill="x", expand=True)
        cart_scroll.pack(side="left", fill="y")

        cart_row = ttk.Frame(self)
        cart_row.pack(anchor="w", padx=16, pady=(0, 4))
        ttk.Label(cart_row, text="Количество:").pack(side="left")
        self.qty_var = tk.StringVar(value="1")
        ttk.Entry(cart_row, textvariable=self.qty_var, width=6).pack(
            side="left", padx=(4, 8)
        )
        ttk.Button(
            cart_row, text="Применить к выбранным", command=self._apply_qty
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            cart_row, text="Убрать из предложения", command=self._remove_selected
        ).pack(side="left")

        discount_and_totals = ttk.Frame(self)
        discount_and_totals.pack(fill="x", padx=16, pady=(2, 4))
        ttk.Label(discount_and_totals, text="Скидка, %:").pack(side="left")
        self.discount_var = tk.StringVar(value="0")
        # Пересчет итогов после каждого изменения скидки.
        self.discount_var.trace_add("write", lambda *args: self._refresh_totals())
        ttk.Entry(
            discount_and_totals, textvariable=self.discount_var, width=6
        ).pack(side="left", padx=(4, 14))
        self.totals_label = ttk.Label(
            discount_and_totals, foreground="#153a5e",
            font=("TkDefaultFont", 10, "bold"), justify="left",
        )
        self.totals_label.pack(side="left")

    # ─── Реквизиты ────────────────────────────────────────────────────

    def _build_details_section(self) -> None:
        ttk.Label(self, text="Реквизиты (все поля необязательные):",
                  font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", padx=16, pady=(6, 2))
        grid = ttk.Frame(self)
        grid.pack(anchor="w", padx=16, pady=(0, 4))
        self.detail_vars: dict[str, tk.StringVar] = {}
        for row, (key, label) in enumerate(DETAIL_FIELDS):
            ttk.Label(grid, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value="")
            self.detail_vars[key] = var
            ttk.Entry(grid, textvariable=var, width=52).grid(
                row=row, column=1, sticky="we", padx=(8, 0), pady=2
            )
        comment_row = len(DETAIL_FIELDS)
        ttk.Label(grid, text="Комментарий (необязательно)").grid(
            row=comment_row, column=0, sticky="w", pady=2)
        self.detail_vars["comment"] = tk.StringVar(value="")
        ttk.Entry(grid, textvariable=self.detail_vars["comment"], width=52).grid(
            row=comment_row, column=1, sticky="we", padx=(8, 0), pady=2)
        self.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

    # ─── Действия ─────────────────────────────────────────────────────

    def _build_actions(self) -> None:
        buttons = ttk.Frame(self)
        buttons.pack(anchor="w", padx=16, pady=(8, 4))
        ttk.Button(buttons, text="Заполнить пример", command=self._fill_demo).pack(
            side="left", padx=(0, 6))
        self.create_btn = ttk.Button(
            buttons, text="Сформировать коммерческое предложение",
            command=self._create_pdf,
        )
        self.create_btn.pack(side="left")

        self.status = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self.status, foreground="#1c6b32",
            wraplength=560, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

    def _fill_demo(self) -> None:
        """Заполняет пример целиком: реквизиты, состав из реального каталога, скидка.

        Если каталог еще не загружен — сначала загружается демонстрационный.
        Каталог пользователя не подменяется; товары берутся только те,
        что реально есть в загруженном каталоге.
        """
        for key, value in DEMO_DETAILS.items():
            self.detail_vars[key].set(value)

        if self.catalogue is None:
            demo_path = DATA_DIR / "catalogue.csv"
            if not demo_path.is_file():
                messagebox.showerror(
                    "PDF Studio",
                    f"Демонстрационный каталог не найден: {demo_path}",
                    parent=self,
                )
                return
            self.path_var.set(str(demo_path))
            self._load_file()
        if self.catalogue is None:
            return  # загрузка не удалась — причина уже показана сообщением

        self.cart = quotation.pick_demo_positions(self.catalogue)
        self.discount_var.set("10")
        self._refresh_cart()
        self.status.set(
            "Пример заполнен: реквизиты, позиции из загруженного каталога, "
            "скидка 10 %."
        )

    # ─── Загрузка и фильтрация каталога ───────────────────────────────

    def _choose_file(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Выберите CSV-каталог товаров",
            filetypes=[("CSV-файлы", "*.csv"), ("Все файлы", "*.*")],
            initialdir=str(DATA_DIR),
        )
        if not chosen:
            return
        self.path_var.set(chosen)
        self._load_file()

    def _load_file(self, *, quiet: bool = False) -> None:
        try:
            self.catalogue = quotation.load_catalogue(self.path_var.get())
        except DataError as error:
            self.catalogue = None
            self.stats.set("Каталог не загружен.")
            self.found_var.set("")
            if quiet:
                self.status.set(f"{error}")
            else:
                messagebox.showerror(
                    "PDF Studio — ошибка чтения CSV", str(error), parent=self
                )
            return
        categories = quotation.get_categories(self.catalogue)
        text = (f"Загружено товаров: {len(self.catalogue['items'])}. "
                f"Категорий: {len(categories)}.")
        if self.catalogue["skipped"]:
            text += f" Пропущено некорректных строк: {len(self.catalogue['skipped'])}."
        self.stats.set(text)
        self.category_box["values"] = [quotation.ALL_CATEGORIES] + categories
        self.category_var.set(quotation.ALL_CATEGORIES)
        self.apply_filters()

    def apply_filters(self) -> None:
        if self.catalogue is None:
            return
        category = self.category_var.get() or quotation.ALL_CATEGORIES
        found = quotation.filter_items(
            self.catalogue, category, self.search_var.get()
        )
        self.tree.delete(*self.tree.get_children())
        for item in found:
            self.tree.insert("", "end", iid=item["sku"], values=(
                item["sku"], item["name"], item["category"], item["price"]
            ))
        if not found:
            self.found_var.set("В этой категории ничего не найдено")
        else:
            self.found_var.set(f"Найдено: {len(found)}")

    # ─── Состав предложения ───────────────────────────────────────────

    def _add_selected(self) -> None:
        chosen = self.tree.selection()
        if not chosen:
            messagebox.showinfo(
                "PDF Studio",
                "Отметьте в каталоге хотя бы один товар.",
                parent=self,
            )
            return
        if self.catalogue is None:
            return
        try:
            qty = quotation.parse_quantity(self.qty_var.get())
        except DataError as error:
            messagebox.showerror("PDF Studio — количество", str(error), parent=self)
            return
        by_sku = {item["sku"]: item for item in self.catalogue["items"]}
        added = 0
        for sku in chosen:
            existing = next((row for row in self.cart if row["sku"] == sku), None)
            if existing is not None:
                existing["qty"] += qty  # повторное добавление суммируется
            else:
                self.cart.append({"sku": sku, "qty": qty})
            added += 1
        self._refresh_cart()
        self.status.set(f"Добавлено позиций: {added}.")

    def _apply_qty(self) -> None:
        chosen = self.cart_tree.selection()
        if not chosen:
            messagebox.showinfo(
                "PDF Studio",
                "Отметьте строку в составе предложения.",
                parent=self,
            )
            return
        try:
            qty = quotation.parse_quantity(self.qty_var.get())
        except DataError as error:
            messagebox.showerror("PDF Studio — количество", str(error), parent=self)
            return
        for row in self.cart:
            if row["sku"] in chosen:
                row["qty"] = qty
        self._refresh_cart()

    def _remove_selected(self) -> None:
        chosen = set(self.cart_tree.selection())
        self.cart = [row for row in self.cart if row["sku"] not in chosen]
        self._refresh_cart()

    def _refresh_cart(self) -> None:
        """Перерисовывает состав и пересчитывает итоги."""
        self.cart_tree.delete(*self.cart_tree.get_children())
        if self.cart and self.catalogue is not None:
            by_sku = {item["sku"]: item for item in self.catalogue["items"]}
            for row in self.cart:
                item = by_sku[row["sku"]]
                line_sum = item["price"] * row["qty"]
                self.cart_tree.insert("", "end", iid=row["sku"], values=(
                    row["sku"], item["name"], int(row["qty"]),
                    item["price"], line_sum,
                ))
        self._refresh_totals()

    def _refresh_totals(self) -> None:
        """Обновляет блок итогов; при невалидной скидке выводится прочерк."""
        if not self.cart or self.catalogue is None:
            self.totals_label.config(text="")
            return
        try:
            calc = quotation.calculate_quotation(
                self.catalogue, self.cart, self.discount_var.get()
            )
        except DataError:
            self.totals_label.config(
                text="Итог: — (проверьте количества и скидку)",
                foreground="#a34b2a",
            )
            return
        lines = [f"Итого без скидки: {format_money(calc['subtotal'])} ₽"]
        if calc["discount_pct"] > 0:
            lines.append(
                f"Скидка {calc['discount_pct']} %: "
                f"−{format_money(calc['discount_amount'])} ₽"
            )
        lines.append(f"Итого к оплате: {format_money(calc['grand_total'])} ₽")
        self.totals_label.config(text="  ·  ".join(lines), foreground="#153a5e")

    # ─── Создание PDF ─────────────────────────────────────────────────

    def _create_pdf(self) -> None:
        if self.catalogue is None:
            messagebox.showwarning(
                "PDF Studio", "Сначала выберите CSV-каталог товаров.", parent=self
            )
            return
        if not self.cart:
            messagebox.showwarning(
                "PDF Studio",
                "Состав предложения пуст.\n"
                "Добавьте в него хотя бы один товар из каталога.",
                parent=self,
            )
            return
        details = {key: var.get() for key, var in self.detail_vars.items()}
        self.create_btn.config(state="disabled")
        self.config(cursor="wait")
        try:
            output_path = quotation.create_quotation_pdf(
                self.catalogue, self.cart, self.discount_var.get(), details
            )
        except DataError as error:
            messagebox.showerror("PDF Studio — ошибка", str(error), parent=self)
            return
        finally:
            self.config(cursor="")
            self.create_btn.config(state="normal")
        pdf_output.open_pdf(output_path)
        self.status.set(f"PDF создан: {output_path}")
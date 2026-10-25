import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta

import database
from notifications import send_notification, test_notification

STATUSES = ["Все", "Ожидает", "Готово", "Просрочено", "Отменено"]


class ReminderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Напоминалка")
        self.root.geometry("950x650")
        self.root.minsize(780, 520)

        database.init_db()
        self.notified_ids = set()

        self.title_var = tk.StringVar()
        self.description_var = tk.StringVar()
        self.date_var = tk.StringVar(
            value=(datetime.now() + timedelta(minutes=5)).strftime("%d.%m.%Y %H:%M")
        )
        self.repeat_var = tk.StringVar(value="Не повторять")
        self.filter_var = tk.StringVar(value="Все")

        self._build_ui()
        self.refresh_reminders()
        self.check_reminders()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="НАПОМИНАЛКА", font=("Segoe UI", 18, "bold")).pack(
            anchor="w", pady=(0, 10)
        )

        form = ttk.LabelFrame(main, text="Новое напоминание", padding=10)
        form.pack(fill="x", pady=(0, 10))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Название:").grid(
            row=0, column=0, sticky="w", padx=5, pady=4
        )
        ttk.Entry(form, textvariable=self.title_var).grid(
            row=0, column=1, sticky="ew", padx=5, pady=4
        )

        ttk.Label(form, text="Описание:").grid(
            row=1, column=0, sticky="w", padx=5, pady=4
        )
        ttk.Entry(form, textvariable=self.description_var).grid(
            row=1, column=1, sticky="ew", padx=5, pady=4
        )

        ttk.Label(form, text="Дата и время:").grid(
            row=2, column=0, sticky="w", padx=5, pady=4
        )
        ttk.Entry(form, textvariable=self.date_var, width=22).grid(
            row=2, column=1, sticky="w", padx=5, pady=4
        )
        ttk.Label(form, text="Формат: ДД.ММ.ГГГГ ЧЧ:ММ").grid(
            row=2, column=2, sticky="w", padx=5, pady=4
        )

        ttk.Label(form, text="Повторение:").grid(
            row=3, column=0, sticky="w", padx=5, pady=4
        )
        ttk.Combobox(
            form,
            textvariable=self.repeat_var,
            values=["Не повторять", "Каждые 30 минут", "Каждый час", "Каждый день"],
            state="readonly",
            width=20,
        ).grid(row=3, column=1, sticky="w", padx=5, pady=4)

        buttons = ttk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Button(buttons, text="Добавить", command=self.add_reminder).pack(
            side="left", padx=3
        )

        for minutes in (1, 5, 15, 30):
            ttk.Button(
                buttons,
                text=f"Через {minutes} мин.",
                command=lambda m=minutes: self.set_quick_time(m),
            ).pack(side="left", padx=3)

        ttk.Button(
            buttons, text="Тест уведомления", command=self.run_test_notification
        ).pack(side="left", padx=3)

        filter_frame = ttk.Frame(main)
        filter_frame.pack(fill="x", pady=(0, 6))

        ttk.Label(filter_frame, text="Фильтр по статусу:").pack(side="left")
        filter_box = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_var,
            values=STATUSES,
            state="readonly",
            width=18,
        )
        filter_box.pack(side="left", padx=8)
        filter_box.bind("<<ComboboxSelected>>", lambda event: self.refresh_reminders())

        columns = ("id", "title", "remind_at", "status", "repeat")
        self.tree = ttk.Treeview(main, columns=columns, show="headings", height=12)

        self.tree.heading("id", text="№")
        self.tree.heading("title", text="Название")
        self.tree.heading("remind_at", text="Дата и время")
        self.tree.heading("status", text="Статус")
        self.tree.heading("repeat", text="Повторение")

        self.tree.column("id", width=45, anchor="center")
        self.tree.column("title", width=300)
        self.tree.column("remind_at", width=155, anchor="center")
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("repeat", width=140, anchor="center")

        scrollbar = ttk.Scrollbar(main, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=(8, 0))

        ttk.Button(actions, text="Показать описание", command=self.show_details).pack(
            side="left", padx=3
        )
        ttk.Button(
            actions, text="Готово", command=lambda: self.change_status("Готово")
        ).pack(side="left", padx=3)
        ttk.Button(
            actions, text="Отменить", command=lambda: self.change_status("Отменено")
        ).pack(side="left", padx=3)
        ttk.Button(actions, text="Удалить", command=self.delete_selected).pack(
            side="left", padx=3
        )

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def set_quick_time(self, minutes):
        moment = datetime.now() + timedelta(minutes=minutes)
        self.date_var.set(moment.strftime("%d.%m.%Y %H:%M"))

    def add_reminder(self):
        title = self.title_var.get().strip()
        description = self.description_var.get().strip()

        if not title:
            messagebox.showwarning("Проверка данных", "Введите название напоминания.")
            return

        try:
            remind_at = datetime.strptime(self.date_var.get().strip(), "%d.%m.%Y %H:%M")
        except ValueError:
            messagebox.showerror(
                "Ошибка даты",
                "Введите дату в формате ДД.ММ.ГГГГ ЧЧ:ММ.",
            )
            return

        if remind_at <= datetime.now():
            messagebox.showwarning(
                "Проверка времени",
                "Укажите дату и время в будущем.",
            )
            return

        repeat_options = {
            "Не повторять": 0,
            "Каждые 30 минут": 30,
            "Каждый час": 60,
            "Каждый день": 1440,
        }
        repeat_minutes = repeat_options[self.repeat_var.get()]

        try:
            database.add_reminder(
                title,
                description,
                remind_at.isoformat(timespec="seconds"),
                repeat_minutes,
            )
        except (ValueError, Exception) as error:
            messagebox.showerror("Ошибка", str(error))
            return

        self.title_var.set("")
        self.description_var.set("")
        self.repeat_var.set("Не повторять")
        self.refresh_reminders()
        messagebox.showinfo("Готово", "Напоминание добавлено.")

    def refresh_reminders(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        reminders = database.get_reminders(self.filter_var.get())

        repeat_labels = {
            0: "Нет",
            30: "Каждые 30 минут",
            60: "Каждый час",
            1440: "Каждый день",
        }

        for reminder in reminders:
            try:
                moment = datetime.fromisoformat(reminder["remind_at"])
                formatted_time = moment.strftime("%d.%m.%Y %H:%M")
            except ValueError:
                formatted_time = reminder["remind_at"]

            self.tree.insert(
                "",
                "end",
                iid=str(reminder["id"]),
                values=(
                    reminder["id"],
                    reminder["title"],
                    formatted_time,
                    reminder["status"],
                    repeat_labels.get(reminder["repeat_minutes"], "Повтор"),
                ),
            )

    def get_selected_reminder(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(
                "Нет выбора", "Сначала выберите напоминание в списке."
            )
            return None

        return int(selected[0])

    def change_status(self, status):
        reminder_id = self.get_selected_reminder()
        if reminder_id is None:
            return

        database.update_status(reminder_id, status)
        self.refresh_reminders()

    def delete_selected(self):
        reminder_id = self.get_selected_reminder()
        if reminder_id is None:
            return

        if messagebox.askyesno("Подтверждение", "Удалить выбранное напоминание?"):
            database.delete_reminder(reminder_id)
            self.notified_ids.discard(reminder_id)
            self.refresh_reminders()

    def show_details(self):
        reminder_id = self.get_selected_reminder()
        if reminder_id is None:
            return

        reminders = database.get_reminders()
        reminder = next((item for item in reminders if item["id"] == reminder_id), None)

        if reminder:
            messagebox.showinfo(
                reminder["title"],
                reminder["description"] or "Описание не указано.",
            )

    def run_test_notification(self):
        if not test_notification():
            messagebox.showwarning(
                "Уведомление", "Не удалось отправить системное уведомление."
            )

    def check_reminders(self):
        """Проверяет наступление времени и планирует повторения."""
        now = datetime.now()

        for reminder in database.get_reminders():
            if reminder["status"] != "Ожидает":
                continue

            try:
                remind_at = datetime.fromisoformat(reminder["remind_at"])
            except ValueError:
                continue

            reminder_id = reminder["id"]

            if remind_at <= now and reminder_id not in self.notified_ids:
                sent = send_notification(
                    reminder["title"],
                    reminder["description"] or "Время выполнить напоминание!",
                )
                self.notified_ids.add(reminder_id)

                repeat_minutes = reminder["repeat_minutes"]

                if repeat_minutes > 0:
                    next_time = now + timedelta(minutes=repeat_minutes)
                    with database.get_connection() as connection:
                        connection.execute(
                            """
                            UPDATE reminders
                            SET remind_at = ?
                            WHERE id = ?
                            """,
                            (
                                next_time.isoformat(timespec="seconds"),
                                reminder_id,
                            ),
                        )
                else:
                    database.update_status(reminder_id, "Просрочено")

        self.refresh_reminders()
        self.root.after(15000, self.check_reminders)

    def on_close(self):
        self.root.destroy()


def run_app():
    root = tk.Tk()
    ReminderApp(root)
    root.mainloop()

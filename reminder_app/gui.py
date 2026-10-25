import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta

import database
from notifications import test_notification

STATUSES = ["Все", "Ожидает", "Готово", "Отменено"]

BEFORE_OPTIONS = [
    ("За 60 минут", 60),
    ("За 30 минут", 30),
    ("За 15 минут", 15),
    ("За 5 минут", 5),
]

AFTER_OPTIONS = [
    ("Через 5 минут", 5),
    ("Через 15 минут", 15),
    ("Через 30 минут", 30),
    ("Через 60 минут", 60),
]


class ReminderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Напоминалка")
        self.root.geometry("1000x760")
        self.root.minsize(820, 650)

        database.init_db()

        self.title_var = tk.StringVar()
        self.description_var = tk.StringVar()
        self.date_var = tk.StringVar(
            value=(datetime.now() + timedelta(minutes=5)).strftime("%d.%m.%Y %H:%M")
        )
        self.filter_var = tk.StringVar(value="Все")

        self.before_vars = {
            minutes: tk.BooleanVar(value=False) for _, minutes in BEFORE_OPTIONS
        }
        self.at_time_var = tk.BooleanVar(value=True)
        self.after_vars = {
            minutes: tk.BooleanVar(value=minutes == False)
            for _, minutes in AFTER_OPTIONS
        }

        self.popup = None
        self.popup_events = {}
        self.popup_rows = {}
        self.snooze_var = tk.StringVar(value="")

        self._build_ui()
        self.refresh_reminders()
        self.check_reminders()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="НАПОМИНАЛКА",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        form = ttk.LabelFrame(
            main,
            text="1. Новое напоминание",
            padding=10,
        )
        form.pack(fill="x", pady=(0, 10))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Название:").grid(
            row=0, column=0, sticky="w", padx=5, pady=4
        )
        ttk.Entry(form, textvariable=self.title_var).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=5, pady=4
        )

        ttk.Label(form, text="Описание:").grid(
            row=1, column=0, sticky="w", padx=5, pady=4
        )
        ttk.Entry(form, textvariable=self.description_var).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=5, pady=4
        )

        ttk.Label(form, text="Контрольное время X:").grid(
            row=2, column=0, sticky="w", padx=5, pady=4
        )
        ttk.Entry(form, textvariable=self.date_var, width=22).grid(
            row=2, column=1, sticky="w", padx=5, pady=4
        )
        ttk.Label(
            form,
            text="ДД.ММ.ГГГГ ЧЧ:ММ",
        ).grid(row=2, column=2, sticky="w", padx=5, pady=4)

        schedule = ttk.LabelFrame(
            form,
            text="2. Когда напоминать относительно времени X",
            padding=8,
        )
        schedule.grid(row=3, column=0, columnspan=3, sticky="ew", padx=5, pady=(10, 5))
        schedule.columnconfigure(0, weight=1)
        schedule.columnconfigure(1, weight=1)
        schedule.columnconfigure(2, weight=1)

        before_frame = ttk.LabelFrame(schedule, text="До X", padding=6)
        before_frame.grid(row=0, column=0, sticky="nsew", padx=4)
        for label, minutes in BEFORE_OPTIONS:
            ttk.Checkbutton(
                before_frame,
                text=label,
                variable=self.before_vars[minutes],
            ).pack(anchor="w", pady=2)

        at_frame = ttk.LabelFrame(schedule, text="В момент X", padding=6)
        at_frame.grid(row=0, column=1, sticky="nsew", padx=4)
        ttk.Checkbutton(
            at_frame,
            text="В назначенное время",
            variable=self.at_time_var,
        ).pack(anchor="w", pady=2)

        after_frame = ttk.LabelFrame(schedule, text="После X", padding=6)
        after_frame.grid(row=0, column=2, sticky="nsew", padx=4)
        for label, minutes in AFTER_OPTIONS:
            ttk.Checkbutton(
                after_frame,
                text=label,
                variable=self.after_vars[minutes],
            ).pack(anchor="w", pady=2)

        ttk.Label(
            form,
            text=(
                "Можно выбрать несколько интервалов. "
                "После выполнения задачи оставшиеся сигналы отменяются."
            ),
            wraplength=850,
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=5, pady=5)

        form_buttons = ttk.Frame(form)
        form_buttons.grid(
            row=5, column=0, columnspan=3, sticky="w", padx=5, pady=(5, 0)
        )
        ttk.Button(
            form_buttons,
            text="Добавить напоминание",
            command=self.add_reminder,
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            form_buttons,
            text="Очистить поля",
            command=self.clear_form,
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            form_buttons,
            text="Тест уведомления",
            command=self.run_test_notification,
        ).pack(side="left")

        list_frame = ttk.LabelFrame(main, text="3. Список задач", padding=8)
        list_frame.pack(fill="both", expand=True)

        filter_frame = ttk.Frame(list_frame)
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
        filter_box.bind(
            "<<ComboboxSelected>>",
            lambda event: self.refresh_reminders(),
        )

        columns = ("id", "title", "remind_at", "status", "pending")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=10,
        )

        headings = {
            "id": "№",
            "title": "Название",
            "remind_at": "Контрольное время X",
            "status": "Статус",
            "pending": "Сигналов осталось",
        }
        for column, heading in headings.items():
            self.tree.heading(column, text=heading)

        self.tree.column("id", width=45, anchor="center")
        self.tree.column("title", width=260)
        self.tree.column("remind_at", width=180, anchor="center")
        self.tree.column("status", width=110, anchor="center")
        self.tree.column("pending", width=130, anchor="center")

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=(8, 0))

        ttk.Button(
            actions,
            text="Показать описание",
            command=self.show_details,
        ).pack(side="left", padx=3)

        ttk.Button(
            actions,
            text="Выполнено",
            command=self.complete_selected,
        ).pack(side="left", padx=3)

        ttk.Button(
            actions,
            text="Отменить задачу",
            command=lambda: self.change_status("Отменено"),
        ).pack(side="left", padx=3)

        ttk.Button(
            actions,
            text="Удалить",
            command=self.delete_selected,
        ).pack(side="left", padx=3)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def clear_form(self):
        self.title_var.set("")
        self.description_var.set("")
        self.date_var.set(
            (datetime.now() + timedelta(minutes=5)).strftime("%d.%m.%Y %H:%M")
        )
        for variable in self.before_vars.values():
            variable.set(False)
        self.at_time_var.set(True)
        for variable in self.after_vars.values():
            variable.set(False)
        self.after_vars[15].set(True)

    def add_reminder(self):
        title = self.title_var.get().strip()
        description = self.description_var.get().strip()

        if not title:
            messagebox.showwarning(
                "Не заполнено название",
                "Введи название напоминания.",
            )
            return

        try:
            control_time = datetime.strptime(
                self.date_var.get().strip(),
                "%d.%m.%Y %H:%M",
            )
        except ValueError:
            messagebox.showerror(
                "Неверная дата",
                "Используй формат ДД.ММ.ГГГГ ЧЧ:ММ.",
            )
            return

        selected_offsets = []
        for minutes, variable in self.before_vars.items():
            if variable.get():
                selected_offsets.append((-minutes, "До X"))

        if self.at_time_var.get():
            selected_offsets.append((0, "В X"))

        for minutes, variable in self.after_vars.items():
            if variable.get():
                selected_offsets.append((minutes, "После X"))

        if not selected_offsets:
            messagebox.showwarning(
                "Нет сигналов",
                "Выбери хотя бы один момент напоминания.",
            )
            return

        now = datetime.now()
        event_times = []
        for offset, event_type in selected_offsets:
            event_time = control_time + timedelta(minutes=offset)
            if event_time < now:
                continue
            event_times.append(
                (
                    event_time.isoformat(timespec="seconds"),
                    event_type,
                )
            )

        if not event_times:
            messagebox.showwarning(
                "Время прошло",
                "Все выбранные моменты напоминания уже прошли. "
                "Укажи будущее контрольное время или выбери другие интервалы.",
            )
            return

        try:
            database.add_reminder(
                title,
                description,
                control_time.isoformat(timespec="seconds"),
                event_times,
            )
        except (ValueError, Exception) as error:
            messagebox.showerror(
                "Ошибка",
                f"Не удалось добавить напоминание:\n{error}",
            )
            return

        self.refresh_reminders()
        self.clear_form()
        messagebox.showinfo(
            "Добавлено",
            f"Напоминание «{title}» добавлено.",
        )

    def refresh_reminders(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for reminder in database.get_reminders(self.filter_var.get()):
            self.tree.insert(
                "",
                "end",
                values=(
                    reminder["id"],
                    reminder["title"],
                    datetime.fromisoformat(reminder["remind_at"]).strftime(
                        "%d.%m.%Y %H:%M"
                    ),
                    reminder["status"],
                    reminder["pending_events"],
                ),
            )

    def selected_reminder(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning(
                "Не выбрана задача",
                "Сначала выбери задачу в списке.",
            )
            return None

        values = self.tree.item(selection[0], "values")
        reminder_id = int(values[0])
        for reminder in database.get_reminders():
            if reminder["id"] == reminder_id:
                return reminder
        return None

    def show_details(self):
        reminder = self.selected_reminder()
        if reminder is None:
            return

        messagebox.showinfo(
            reminder["title"],
            f"Описание: {reminder['description'] or 'Нет'}\n"
            f"Контрольное время: {reminder['remind_at']}\n"
            f"Статус: {reminder['status']}\n"
            f"Ожидающих сигналов: {reminder['pending_events']}",
        )

    def complete_selected(self):
        reminder = self.selected_reminder()
        if reminder is None:
            return
        database.complete_reminder(reminder["id"])
        self.refresh_reminders()

    def change_status(self, status):
        reminder = self.selected_reminder()
        if reminder is None:
            return
        database.change_status(reminder["id"], status)
        self.refresh_reminders()

    def delete_selected(self):
        reminder = self.selected_reminder()
        if reminder is None:
            return

        if messagebox.askyesno(
            "Удалить напоминание?",
            f"Удалить «{reminder['title']}»?",
        ):
            database.delete_reminder(reminder["id"])
            self.refresh_reminders()

    def check_reminders(self):
        now_text = datetime.now().isoformat(timespec="seconds")
        due_events = database.get_due_events(now_text)

        if due_events:
            self.show_due_events(due_events)

        self.refresh_reminders()
        self.root.after(5000, self.check_reminders)

    def show_due_events(self, events):
        if self.popup is None or not self.popup.winfo_exists():
            self.popup = tk.Toplevel(self.root)
            self.popup.title("Напоминания требуют внимания")
            self.popup.geometry("540x420")
            self.popup.minsize(420, 300)
            self.popup.attributes("-topmost", True)
            self.popup.protocol("WM_DELETE_WINDOW", self.close_popup)

            container = ttk.Frame(self.popup, padding=12)
            container.pack(fill="both", expand=True)

            ttk.Label(
                container,
                text="Напоминания",
                font=("Segoe UI", 15, "bold"),
            ).pack(anchor="w", pady=(0, 8))

            self.popup_rows = {}
            self.popup_events = {}

            self.popup_list = ttk.Frame(container)
            self.popup_list.pack(fill="both", expand=True)

            controls = ttk.Frame(container)
            controls.pack(fill="x", pady=(10, 0))

            ttk.Label(controls, text="Отложить на:").pack(side="left")

            snooze_box = ttk.Combobox(
                controls,
                textvariable=self.snooze_var,
                values=["5 минут", "15 минут", "30 минут", "60 минут"],
                state="readonly",
                width=12,
            )
            snooze_box.pack(side="left", padx=6)

            snooze_box.set("")

            ttk.Button(
                controls,
                text="Закрыть окно",
                command=self.close_popup,
            ).pack(side="right")

        # Группируем наступившие сигналы по задачам.
        grouped_events = {}
        for event in events:
            reminder_id = event["reminder_id"]
            grouped_events.setdefault(reminder_id, []).append(event)

        for reminder_id, task_events in grouped_events.items():
            # Если карточка этой задачи уже открыта, добавляем
            # только новые сигналы в ее список.
            existing = self.popup_events.get(reminder_id)

            if existing is not None:
                known_ids = {e["event_id"] for e in existing}
                existing.extend(
                    e for e in task_events if e["event_id"] not in known_ids
                )
                continue

            first_event = task_events[0]
            row = ttk.LabelFrame(
                self.popup_list,
                text=first_event["title"],
                padding=8,
            )
            row.pack(fill="x", pady=4)

            ttk.Label(
                row,
                text=first_event["description"] or "Время выполнить задачу.",
                wraplength=440,
            ).pack(anchor="w", pady=(0, 6))

            signals_text = "\n".join(
                f"{event['event_type']} · {event['event_at']}"
                for event in task_events
            )
            signal_label = ttk.Label(
                row,
                text=f"Наступившие сигналы:\n{signals_text}",
                wraplength=440,
                justify="left",
            )
            signal_label.pack(anchor="w", pady=(0, 6))

            buttons = ttk.Frame(row)
            buttons.pack(fill="x")

            ttk.Button(
                buttons,
                text="Выполнено",
                command=lambda rid=reminder_id: self.complete_popup_reminder_by_id(rid),
            ).pack(side="left", padx=(0, 6))

            ttk.Button(
                buttons,
                text="Напомнить позже",
                command=lambda rid=reminder_id: self.postpone_popup_reminder_by_id(rid),
            ).pack(side="left")

            self.popup_events[reminder_id] = list(task_events)
            self.popup_rows[reminder_id] = row

        self.popup.deiconify()
        self.popup.lift()
        self.popup.attributes("-topmost", True)
        self.popup.focus_force()

    def complete_popup_reminder_by_id(self, reminder_id):
        """Завершает задачу и убирает ее карточку."""
        database.complete_reminder(reminder_id)
        self.remove_popup_reminder(reminder_id)
        self.refresh_reminders()

    def postpone_popup_reminder_by_id(self, reminder_id):
        """Переносит все наступившие сигналы выбранной задачи."""
        events = self.popup_events.get(reminder_id, [])
        if not events:
            return

        choice = self.snooze_var.get()

        if not choice:
            messagebox.showwarning(
                "Не выбран интервал",
                "Сначала выбери, на сколько минут отложить напоминание.",
                parent=self.popup,
            )
            return
        minutes = int(choice.split()[0])
        new_time = datetime.now() + timedelta(minutes=minutes)

        # Переносим первый сигнал. Остальные сигналы этой задачи
        # сохраняются, чтобы не потерять выбранное расписание.
        event = events[0]
        database.postpone_event(
            event["event_id"],
            new_time.isoformat(timespec="seconds"),
        )

        self.remove_popup_reminder(reminder_id)
        self.refresh_reminders()

    def remove_popup_reminder(self, reminder_id):
        """Убирает карточку задачи из окна напоминаний."""
        row = self.popup_rows.pop(reminder_id, None)
        if row is not None:
            row.destroy()

        self.popup_events.pop(reminder_id, None)

        if self.popup is not None and self.popup.winfo_exists():
            if not self.popup_events:
                self.popup.destroy()
                self.popup = None

    def close_popup(self):
        """Скрывает окно, не отмечая задачи выполненными."""
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.withdraw()

    def run_test_notification(self):
        test_notification()
        messagebox.showinfo(
            "Проверка",
            "Запрос тестового системного уведомления отправлен.",
        )

    def on_close(self):
        self.root.destroy()


def run_app():
    root = tk.Tk()
    ReminderApp(root)
    root.mainloop()

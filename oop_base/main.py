"""OOP_base — учебная консольная система управления задачами Todo.

Три класса:
    User    — пользователь системы, владеет проектами.
    Project — проект, объединяет задачи.
    Task    — отдельная задача.

Каждый объект отвечает за собственные данные и действия.
Объекты взаимодействуют только через методы и свойства.
Все данные хранятся в памяти.

Запуск: python main.py
"""


import re
from datetime import date


# ---------------------------------------------------------------------------
# Task — отдельная задача
# ---------------------------------------------------------------------------

# Допустимые статусы задачи. Задаем их в одном месте, чтобы не расползались по коду.
ALLOWED_STATUSES = ("todo", "in_progress", "done")


class Task:
    """Отдельная задача внутри проекта.

    Знает только о своих данных: названии, описании, сроке и статусе.
    ID задачи назначает проект при её добавлении.
    """

    def __init__(self, title, description, task_id, due_date=None):
        """Создать задачу.

        title       — название задачи (непустая строка);
        description — описание задачи (непустая строка);
        task_id     — число, назначается проектом;
        due_date    — строка 'YYYY-MM-DD' или None (срок не задан).
        """
        self._check_text(title, "Название задачи")
        self._check_text(description, "Описание задачи")

        self._id = task_id
        self._title = title
        self._description = description
        self._due_date = self._parse_date(due_date)
        self._status = "todo"

    # --- проверка и разбор входных данных ---------------------------------

    # Строгий формат срока: ровно YYYY-MM-DD, без вариантов без разделителей.
    _DATE_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    @staticmethod
    def _parse_date(due_date):
        """Преобразовать строку 'YYYY-MM-DD' в объект date (или None)."""
        if due_date is None:
            return None
        if not isinstance(due_date, str) or not Task._DATE_FORMAT.match(due_date):
            raise ValueError(f"Срок: '{due_date}' не является датой формата 'YYYY-MM-DD'")
        try:
            return date.fromisoformat(due_date)
        except ValueError:
            raise ValueError(f"Срок: '{due_date}' не является корректной датой формата 'YYYY-MM-DD'")

    @staticmethod
    def _check_text(value, field_name):
        """Проверить строку: не None, не пустая и не из одних пробелов."""
        if not isinstance(value, str):
            raise ValueError(f"{field_name}: ожидается строка, получено {type(value).__name__}")
        if not value.strip():
            raise ValueError(f"{field_name}: не может быть пустой строкой")

    # --- свойства для чтения ----------------------------------------------

    @property
    def id(self):
        return self._id

    @property
    def title(self):
        return self._title

    @property
    def description(self):
        return self._description

    @property
    def due_date(self):
        """Срок задачи: как строку 'YYYY-MM-DD' или None."""
        return self._due_date.isoformat() if self._due_date else None

    @property
    def status(self):
        return self._status

    @property
    def info(self):
        """Краткая сводка о задаче одной строкой."""
        when = self.due_date if self._due_date else "без срока"
        return f"[#{self._id}] {self._title} — {self._description} ({when}, статус: {self._status})"

    # --- действия ----------------------------------------------------------

    def change_description(self, new_description):
        """Изменить описание задачи."""
        self._check_text(new_description, "Описание задачи")
        self._description = new_description

    def change_due_date(self, new_due_date):
        """Изменить срок задачи (строка 'YYYY-MM-DD' или None)."""
        self._due_date = self._parse_date(new_due_date)

    def set_status(self, new_status):
        """Установить статус задачи: todo, in_progress или done."""
        if new_status not in ALLOWED_STATUSES:
            allowed = ", ".join(ALLOWED_STATUSES)
            raise ValueError(f"Статус: неизвестное значение '{new_status}' (разрешены: {allowed})")
        self._status = new_status

    def complete(self):
        """Отметить задачу выполненной."""
        self.set_status("done")


# ---------------------------------------------------------------------------
# Project — проект, объединяющий задачи
# ---------------------------------------------------------------------------

class Project:
    """Проект пользователя: список задач.

    Сам генерирует ID задач и умеет считать прогресс по выполненным задачам.
    """

    # Счётчик ID проектов, общий для всех экземпляров Project.
    _next_project_id = 1

    # Счётчик ID задач внутри одного конкретного проекта.
    def __init__(self, name):
        self._check_name(name)
        self._id = Project._next_project_id
        Project._next_project_id += 1
        self._name = name
        self._tasks = []
        self._next_task_id = 1

    @staticmethod
    def _check_name(name):
        if not isinstance(name, str):
            raise ValueError(f"Название проекта: ожидается строка, получено {type(name).__name__}")
        if not name.strip():
            raise ValueError("Название проекта: не может быть пустой строкой")

    # --- свойства для чтения ----------------------------------------------

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @property
    def tasks(self):
        """Копия списка задач — снаружи его нельзя подменить в обход методов."""
        return list(self._tasks)

    @property
    def progress(self):
        """Процент выполненных задач (0–100). Пустой проект имеет прогресс 0."""
        if not self._tasks:
            return 0
        done = sum(1 for task in self._tasks if task.status == "done")
        return round(done * 100 / len(self._tasks))

    @property
    def info(self):
        """Краткая сводка о проекте одной строкой."""
        return f"[Проект #{self._id}] «{self._name}» — задач: {len(self._tasks)}, прогресс: {self.progress}%"

    # --- действия ----------------------------------------------------------

    def add_task(self, title, description, due_date=None):
        """Создать новую задачу в проекте и вернуть её."""
        task = Task(title, description, self._next_task_id, due_date)
        self._next_task_id += 1
        self._tasks.append(task)
        return task

    def get_task_by_id(self, task_id):
        """Найти задачу по ID. Если задачи нет — вернёт None."""
        # bool — подкласс int в Python, поэтому исключаем его явно.
        if isinstance(task_id, bool) or not isinstance(task_id, int):
            raise ValueError("ID задачи: ожидается целое число")
        for task in self._tasks:
            if task.id == task_id:
                return task
        return None

    def remove_task(self, task_id):
        """Удалить задачу по ID. Если задачи нет — KeyError."""
        # bool — подкласс int в Python, поэтому исключаем его явно.
        if isinstance(task_id, bool) or not isinstance(task_id, int):
            raise ValueError("ID задачи: ожидается целое число")
        for task in self._tasks:
            if task.id == task_id:
                self._tasks.remove(task)
                return task
        raise KeyError(f"Задача с ID {task_id} не найдена в проекте «{self._name}»")

    def mark_task_status(self, task_id, status):
        """Изменить статус задачи по её ID."""
        task = self.get_task_by_id(task_id)
        if task is None:
            raise KeyError(f"Задача с ID {task_id} не найдена в проекте «{self._name}»")
        task.set_status(status)
        return task

    def complete_task(self, task_id):
        """Отметить задачу выполненной по её ID."""
        return self.mark_task_status(task_id, "done")

    def find_tasks_by_status(self, status):
        """Вернуть список задач проекта с указанным статусом."""
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"Статус: неизвестное значение '{status}'")
        return [task for task in self._tasks if task.status == status]


# ---------------------------------------------------------------------------
# User — пользователь системы
# ---------------------------------------------------------------------------

class User:
    """Пользователь системы: владеет списком проектов."""

    def __init__(self, name):
        self._check_name(name)
        self._name = name
        self._projects = []

    @staticmethod
    def _check_name(name):
        if not isinstance(name, str):
            raise ValueError(f"Имя пользователя: ожидается строка, получено {type(name).__name__}")
        if not name.strip():
            raise ValueError("Имя пользователя: не может быть пустой строкой")

    # --- свойства для чтения ----------------------------------------------

    @property
    def name(self):
        return self._name

    @property
    def projects(self):
        """Копия списка проектов — снаружи его нельзя подменить в обход методов."""
        return list(self._projects)

    @property
    def info(self):
        """Краткая сводка о пользователе одной строкой."""
        return f"Пользователь «{self._name}» — проектов: {len(self._projects)}"

    # --- действия ----------------------------------------------------------

    def create_project(self, name):
        """Создать проект с проверкой на дубликат названия и добавить в список.

        Сначала проверяется дубликат (чтобы неудачная попытка не расходовала
        ID проекта), затем объект создается конструктором Project — проверку
        самого названия делает он, без обращения к приватным методам.
        """
        if self.find_project_by_name(name) is not None:
            raise ValueError(f"Проект с названием «{name}» уже существует у пользователя «{self._name}»")
        project = Project(name)
        self._projects.append(project)
        return project

    def add_project(self, project):
        """Добавить уже созданный проект (для объединения владельцев проектов)."""
        if not isinstance(project, Project):
            raise ValueError("add_project: ожидается объект Project")
        if self.find_project_by_name(project.name) is not None:
            raise ValueError(f"Проект с названием «{project.name}» уже существует у пользователя «{self._name}»")
        self._projects.append(project)
        return project

    def get_project_by_id(self, project_id):
        """Найти проект по ID. Если проекта нет — вернёт None."""
        # bool — подкласс int в Python, поэтому исключаем его явно.
        if isinstance(project_id, bool) or not isinstance(project_id, int):
            raise ValueError("ID проекта: ожидается целое число")
        for project in self._projects:
            if project.id == project_id:
                return project
        return None

    def find_project_by_name(self, name):
        """Найти проект по точному названию. Если проекта нет — вернёт None."""
        for project in self._projects:
            if project.name == name:
                return project
        return None

    def remove_project(self, project_id):
        """Удалить проект по ID. Если проекта нет — KeyError."""
        # bool — подкласс int в Python, поэтому исключаем его явно.
        if isinstance(project_id, bool) or not isinstance(project_id, int):
            raise ValueError("ID проекта: ожидается целое число")
        for project in self._projects:
            if project.id == project_id:
                self._projects.remove(project)
                return project
        raise KeyError(f"Проект с ID {project_id} не найден у пользователя «{self._name}»")


# ---------------------------------------------------------------------------
# Демонстрационный сценарий
# ---------------------------------------------------------------------------

def demo():
    """Автоматическая демонстрация возможностей системы управления задачами."""

    print("=" * 60)
    print("Демонстрация OOP_base: пользователь, проекты, задачи")
    print("=" * 60)

    # 1. Создание пользователя и проектов (включая попытку пустого имени)
    try:
        user = User("Анна")
        print("\n1) Создан пользователь:", user.info)
    except ValueError as error:
        print("Ошибка:", error)

    try:
        User("   ")  # некорректное имя пользователя
    except ValueError as error:
        print("   Попытка создать пользователя с пустым именем -> ValueError:", error)

    project_course = user.create_project("Курс вайб-кодинга")
    project_repair = user.create_project("Ремонт")
    print("   Проекты пользователя:", [p.name for p in user.projects])

    try:
        user.create_project("")  # некорректное название
    except ValueError as error:
        print("   Попытка создать проект с пустым названием -> ValueError:", error)

    try:
        user.create_project("Ремонт")  # дубликат названия
    except ValueError as error:
        print("   Попытка создать дубликат проекта -> ValueError:", error)

    # 2. Добавление задач
    print("\n2) Добавляем задачи в проект «%s»" % project_course.name)
    task1 = project_course.add_task("ДЗ VPb04: объектное мышление",
                                    "Создать классы User, Project, Task",
                                    "2026-11-20")
    task2 = project_course.add_task("Пройти тест по ООП", "Тема: классы и объекты")
    task3 = project_course.add_task("Разобрать pydantic", "Смотреть запись вебинара", "2026-11-25")
    for task in project_course.tasks:
        print("   ", task.info)

    # 3. Изменение описания, срока и статуса
    print("\n3) Изменяем описание и срок задачи #%d" % task1.id)
    task1.change_description("Классы готовы — написать тесты")
    task1.change_due_date("2026-11-22")
    print("   ", task1.info)

    print("   Меняем статус задачи #%d: todo -> in_progress" % task2.id)
    task2.set_status("in_progress")
    print("   ", task2.info)

    try:
        task2.set_status("cancelled")  # неизвестный статус
    except ValueError as error:
        print("   Попытка установить статус 'cancelled' -> ValueError:", error)

    try:
        task2.change_due_date("22-11-2026")  # неверный формат даты
    except ValueError as error:
        print("   Попытка задать срок в неверном формате -> ValueError:", error)

    # 4. Прогресс проекта
    print("\n4) Прогресс проекта «%s»: %d%%" % (project_course.name, project_course.progress))
    project_course.complete_task(task1.id)
    project_course.complete_task(task2.id)
    print("   После выполнения задач #%d и #%d: %d%%" % (task1.id, task2.id, project_course.progress))

    # Пустой проект
    print("   Пустой проект «%s» — прогресс: %d%%" % (project_repair.name, project_repair.progress))

    # 5. Поиск по ID
    print("\n5) Поиск объектов по ID")
    found_task = project_course.get_task_by_id(task3.id)
    print("   Найдена задача по ID %d: %s" % (task3.id, found_task.title))
    print("   Поиск несуществующей задачи #999 ->", project_course.get_task_by_id(999))
    found_project = user.get_project_by_id(project_repair.id)
    print("   Найден проект по ID %d: %s" % (project_repair.id, found_project.name))

    # 6. Фильтрация по статусу
    print("\n6) Фильтрация задач по статусу")
    done_tasks = project_course.find_tasks_by_status("done")
    print("   Задачи в статусе 'done':", [t.title for t in done_tasks])

    # 7. Удаление объектов
    print("\n7) Удаление объектов")
    project_course.remove_task(task3.id)
    print("   Задача #%d удалена. Осталось задач: %d" % (task3.id, len(project_course.tasks)))
    try:
        project_course.remove_task(task3.id)  # задача уже удалена
    except KeyError as error:
        print("   Попытка удалить несуществующую задачу -> KeyError:", error)

    user.remove_project(project_repair.id)
    print("   Проект #%d удалён. Осталось проектов: %d" % (project_repair.id, len(user.projects)))

    print("\n" + "=" * 60)
    print("Демонстрация завершена")
    print("=" * 60)


if __name__ == "__main__":
    demo()

"""Тесты учебных классов User, Project, Task (стандартный unittest).

Запуск из папки oop_base:
    python -m unittest
"""

import unittest

from main import Task, Project, User


class TaskTests(unittest.TestCase):
    """Проверяем создание задачи, валидацию и изменение данных."""

    def setUp(self):
        self.task = Task("Купить продукты", "Молоко, хлеб", 1, "2026-11-20")

    def test_task_creation_generates_fields(self):
        self.assertEqual(self.task.id, 1)
        self.assertEqual(self.task.title, "Купить продукты")
        self.assertEqual(self.task.description, "Молоко, хлеб")
        self.assertEqual(self.task.due_date, "2026-11-20")
        self.assertEqual(self.task.status, "todo")

    def test_task_without_due_date(self):
        task = Task("Позвонить маме", "Спросить о планах", 2)
        self.assertIsNone(task.due_date)

    def test_empty_title_raises(self):
        for bad in ("", "   "):
            with self.assertRaises(ValueError):
                Task(bad, "Описание", 3)

    def test_empty_description_raises(self):
        with self.assertRaises(ValueError):
            Task("Название", "", 4)

    def test_bad_due_date_raises(self):
        for bad in ("2026-13-01", "22-11-2026", "два ноября", "20261120"):
            with self.assertRaises(ValueError):
                Task("Название", "Описание", 5, bad)

    def test_change_description(self):
        self.task.change_description("Молоко, хлеб, сыр")
        self.assertEqual(self.task.description, "Молоко, хлеб, сыр")

    def test_change_empty_description_raises(self):
        with self.assertRaises(ValueError):
            self.task.change_description("  ")

    def test_change_due_date(self):
        self.task.change_due_date("2026-12-01")
        self.assertEqual(self.task.due_date, "2026-12-01")

    def test_clear_due_date(self):
        self.task.change_due_date(None)
        self.assertIsNone(self.task.due_date)

    def test_set_status_valid(self):
        for status in ("todo", "in_progress", "done"):
            self.task.set_status(status)
            self.assertEqual(self.task.status, status)

    def test_set_status_unknown_raises(self):
        with self.assertRaises(ValueError):
            self.task.set_status("cancelled")

    def test_complete_sets_done(self):
        self.task.complete()
        self.assertEqual(self.task.status, "done")


class ProjectTests(unittest.TestCase):
    """Проверяем проект: задачи, ID, прогресс, поиск и удаление."""

    def setUp(self):
        self.project = Project("Учеба")
        tasks = self.project.tasks  # пусто на старте
        self.assertEqual(tasks, [])

    def test_project_ids_are_auto_and_unique(self):
        other = Project("Другой проект")
        self.assertIsInstance(self.project.id, int)
        self.assertNotEqual(self.project.id, other.id)

    def test_add_task_assigns_sequential_ids(self):
        task1 = self.project.add_task("Задача один", "Описание")
        task2 = self.project.add_task("Задача два", "Описание", "2026-12-01")
        self.assertEqual(task1.id, 1)
        self.assertEqual(task2.id, 2)
        self.assertEqual(len(self.project.tasks), 2)

    def test_add_task_empty_title_raises(self):
        with self.assertRaises(ValueError):
            self.project.add_task("", "Описание")

    def test_empty_project_progress_is_zero(self):
        self.assertEqual(self.project.progress, 0)

    def test_progress_counts_done_tasks(self):
        t1 = self.project.add_task("A", "Описание")
        t2 = self.project.add_task("B", "Описание")
        t3 = self.project.add_task("C", "Описание")
        self.assertEqual(self.project.progress, 0)
        self.project.complete_task(t1.id)  # 1 из 3
        self.assertEqual(self.project.progress, 33)
        self.project.complete_task(t2.id)  # 2 из 3
        self.assertEqual(self.project.progress, 67)
        self.project.complete_task(t3.id)  # 3 из 3
        self.assertEqual(self.project.progress, 100)

    def test_progress_survives_task_removal(self):
        t1 = self.project.add_task("A", "Описание")
        t2 = self.project.add_task("B", "Описание")
        self.project.complete_task(t1.id)
        self.project.remove_task(t2.id)
        self.assertEqual(self.project.progress, 100)

    def test_get_task_by_id_found_and_not_found(self):
        task = self.project.add_task("A", "Описание")
        self.assertIs(self.project.get_task_by_id(task.id), task)
        self.assertIsNone(self.project.get_task_by_id(999))

    def test_get_task_by_id_bad_type_raises(self):
        with self.assertRaises(ValueError):
            self.project.get_task_by_id("1")

    def test_remove_task_removes(self):
        task = self.project.add_task("A", "Описание")
        removed = self.project.remove_task(task.id)
        self.assertIs(removed, task)
        self.assertEqual(self.project.tasks, [])

    def test_remove_missing_task_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.project.remove_task(42)

    def test_mark_task_status(self):
        task = self.project.add_task("A", "Описание")
        self.project.mark_task_status(task.id, "in_progress")
        self.assertEqual(task.status, "in_progress")

    def test_mark_missing_task_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.project.mark_task_status(77, "done")

    def test_find_tasks_by_status(self):
        t1 = self.project.add_task("A", "Описание")
        t2 = self.project.add_task("B", "Описание")
        self.project.complete_task(t2.id)
        found = self.project.find_tasks_by_status("done")
        self.assertEqual(found, [t2])
        self.assertEqual(self.project.find_tasks_by_status("todo"), [t1])

    def test_find_tasks_by_bad_status_raises(self):
        with self.assertRaises(ValueError):
            self.project.find_tasks_by_status("closed")

    def test_tasks_property_returns_copy(self):
        self.project.add_task("A", "Описание")
        snapshot = self.project.tasks
        snapshot.clear()  # пытаемся испортить список снаружи
        self.assertEqual(len(self.project.tasks), 1)


class UserTests(unittest.TestCase):
    """Проверяем пользователя: проекты, поиск, дубликаты, удаление."""

    def setUp(self):
        self.user = User("Анна")

    def test_user_creation_empty_name_raises(self):
        for bad in ("", "   "):
            with self.assertRaises(ValueError):
                User(bad)

    def test_create_project_adds_and_returns(self):
        project = self.user.create_project("Отпуск")
        self.assertEqual(len(self.user.projects), 1)
        self.assertIs(self.user.projects[0], project)

    def test_create_project_empty_name_raises(self):
        with self.assertRaises(ValueError):
            self.user.create_project("  ")

    def test_duplicate_project_name_raises(self):
        self.user.create_project("Отпуск")
        with self.assertRaises(ValueError):
            self.user.create_project("Отпуск")

    def test_add_project_checks_type_and_duplicates(self):
        with self.assertRaises(ValueError):
            self.user.add_project("не проект")
        project = Project("Дом")
        self.assertIs(self.user.add_project(project), project)
        with self.assertRaises(ValueError):
            self.user.add_project(Project("Дом"))

    def test_get_project_by_id(self):
        project = self.user.create_project("Дом")
        self.assertIs(self.user.get_project_by_id(project.id), project)
        self.assertIsNone(self.user.get_project_by_id(999))

    def test_find_project_by_name(self):
        self.user.create_project("Дом")
        found = self.user.find_project_by_name("Дом")
        self.assertIsNotNone(found)
        self.assertIsNone(self.user.find_project_by_name("Баня"))

    def test_remove_project(self):
        project = self.user.create_project("Дом")
        removed = self.user.remove_project(project.id)
        self.assertIs(removed, project)
        self.assertEqual(self.user.projects, [])

    def test_remove_missing_project_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.user.remove_project(123)

    def test_projects_property_returns_copy(self):
        self.user.create_project("Дом")
        snapshot = self.user.projects
        snapshot.clear()
        self.assertEqual(len(self.user.projects), 1)

    def test_user_project_integration(self):
        """Интеграция: пользователь -> проект -> задача -> изменение статуса."""
        project = self.user.create_project("Курс")
        task = project.add_task("ДЗ", "Сделать классы", "2026-11-20")
        project.complete_task(task.id)
        found = self.user.get_project_by_id(project.id)
        self.assertEqual(found.progress, 100)


if __name__ == "__main__":
    unittest.main()

"""
utils.py — логика работы с заметками.

Функции для добавления, вывода и удаления заметок.
Сами данные лежат в database.py — отсюда импортируем notes_db.
"""

from database import notes_db


def add_note(text):
    """Добавляет заметку. Возвращает True, если удалось."""
    # Проверка: нельзя добавить пустую строку
    if not text or not text.strip():
        print("Ошибка: заметка не может быть пустой.")
        return False

    notes_db.append(text.strip())
    print(f"Заметка добавлена (№ {len(notes_db)}).")
    return True


def show_notes():
    """Выводит все заметки на экран с нумерацией."""
    # Проверка: список пуст — выводить нечего
    if not notes_db:
        print("Список заметок пуст.")
        return

    print("\n--- Все заметки ---")
    for number, text in enumerate(notes_db, start=1):
        print(f"{number}. {text}")
    print("-------------------")


def delete_note(number):
    """Удаляет заметку по номеру. Возвращает True, если удалось."""
    # Проверка: удалять нечего, если список пуст
    if not notes_db:
        print("Ошибка: список заметок пуст — удалять нечего.")
        return False

    # Проверка: номер за пределами списка
    if not 1 <= number <= len(notes_db):
        print(f"Ошибка: заметки с номером {number} нет. "
              f"Допустимые номера: 1–{len(notes_db)}.")
        return False

    deleted = notes_db.pop(number - 1)  # в списке нумерация с нуля
    print(f"Удалена заметка № {number}: «{deleted}».")
    return True

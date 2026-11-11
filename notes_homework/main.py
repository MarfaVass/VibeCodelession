"""
main.py — точка входа мини-приложения "Заметки".

Здесь только интерфейс: меню и input.
Логика лежит в utils.py, данные — в database.py.
"""

from utils import add_note, show_notes, delete_note


def main():
    """Точка входа: бесконечный цикл с меню."""
    while True:
        print("\n======= МЕНЮ ========")
        print("1. Добавить заметку")
        print("2. Вывести все заметки")
        print("3. Удалить заметку по номеру")
        print("4. Выход")
        print("=====================")

        choice = input("Выберите пункт меню (1–4): ").strip()

        if choice == "1":
            # Здесь только интерфейс: читаем ввод и передаём в utils
            text = input("Введите текст заметки: ")
            add_note(text)

        elif choice == "2":
            show_notes()

        elif choice == "3":
            show_notes()
            raw = input("Введите номер заметки для удаления: ").strip()

            # Проверка: пользователь ввёл не число
            if not raw.isdigit():
                print("Ошибка: нужно ввести целое число (номер заметки).")
                continue

            delete_note(int(raw))

        elif choice == "4":
            print("Выход. До встречи!")
            break  # выходим из бесконечного цикла

        else:
            # Проверка: неизвестный пункт меню
            print("Ошибка: такого пункта меню нет, введите число от 1 до 4.")


if __name__ == '__main__':
    main()

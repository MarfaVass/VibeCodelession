"""Локальный CLI-менеджер паролей для учебного проекта.

Внимание: это учебный проект, не замена проверенному менеджеру паролей.
Файл ключа .key и база password.db должны храниться вместе в защищённой папке.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sqlite3
import string
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from werkzeug.security import check_password_hash, generate_password_hash

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "password.db"
KEY_PATH = APP_DIR / ".key"

AMBIGUOUS_CHARACTERS = "0OolI1"
ALL_SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?"
UNCOMFORTABLE_SYMBOLS = "[]{};:,.?^"


# ---------- База данных и шифрование ----------


def connect_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Подключается к базе и создает таблицы, если их еще нет."""
    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            master_hash TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL UNIQUE COLLATE NOCASE,
            username TEXT NOT NULL,
            password_encrypted BLOB NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    return conn


def get_cipher(key_path: Path = KEY_PATH) -> Fernet:
    """Загружает существующий ключ или создает новый."""
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(Fernet.generate_key())

        try:
            key_path.chmod(0o600)
        except OSError:
            pass

    return Fernet(key_path.read_bytes().strip())


def ensure_master_password(conn: sqlite3.Connection) -> None:
    """При первом запуске предлагает создать мастер-пароль."""
    row = conn.execute("SELECT master_hash FROM settings WHERE id = 1").fetchone()

    if row:
        return

    print("\nПервый запуск: создайте мастер-пароль.")
    print("Минимальная длина — 12 символов.")

    while True:
        master = getpass.getpass("Новый мастер-пароль: ")

        if len(master) < 12:
            print("Пароль слишком короткий.")
            continue

        confirmation = getpass.getpass("Повторите мастер-пароль: ")

        if master != confirmation:
            print("Пароли не совпадают. Попробуйте еще раз.")
            continue

        password_hash = generate_password_hash(
            master,
            method="pbkdf2:sha256:600000",
        )

        conn.execute(
            "INSERT INTO settings (id, master_hash) VALUES (1, ?)",
            (password_hash,),
        )
        conn.commit()

        print("Мастер-пароль сохранен.")
        return


def authenticate(
    conn: sqlite3.Connection,
    attempts: int = 3,
) -> bool:
    """Проверяет мастер-пароль."""
    ensure_master_password(conn)

    row = conn.execute("SELECT master_hash FROM settings WHERE id = 1").fetchone()

    for _ in range(attempts):
        candidate = getpass.getpass("Мастер-пароль: ")

        if check_password_hash(row[0], candidate):
            return True

        print("Неверный мастер-пароль.")

    print("Превышено количество попыток.")
    return False


# ---------- Генератор паролей ----------


def generate_password(
    length: int = 20,
    exclude_ambiguous: bool = False,
    use_lowercase: bool = True,
    use_uppercase: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
    min_special: int = 0,
    exclude_uncomfortable: bool = False,
) -> str:
    """Генерирует пароль с учетом выбранных настроек."""

    if isinstance(length, bool) or not isinstance(length, int):
        raise ValueError("Длина должна быть целым числом.")

    if not 12 <= length <= 64:
        raise ValueError("Длина пароля должна быть от 12 до 64 символов.")

    flags = (
        use_lowercase,
        use_uppercase,
        use_digits,
        use_symbols,
    )

    if any(not isinstance(flag, bool) for flag in flags):
        raise ValueError("Настройки групп должны быть True или False.")

    if not any(flags):
        raise ValueError("Выберите хотя бы одну группу символов.")

    if isinstance(min_special, bool) or not isinstance(min_special, int):
        raise ValueError("Минимум спецсимволов должен быть целым числом.")

    if not 0 <= min_special <= length:
        raise ValueError("Количество спецсимволов должно быть от 0 до длины пароля.")

    if min_special > 0 and not use_symbols:
        raise ValueError("Включите спецсимволы, чтобы задать их минимум.")

    symbols = ALL_SYMBOLS

    if exclude_uncomfortable:
        symbols = "".join(char for char in symbols if char not in UNCOMFORTABLE_SYMBOLS)

    groups = []

    if use_lowercase:
        groups.append(string.ascii_lowercase)

    if use_uppercase:
        groups.append(string.ascii_uppercase)

    if use_digits:
        groups.append(string.digits)

    if use_symbols:
        groups.append(symbols)

    if exclude_ambiguous:
        groups = [
            "".join(char for char in group if char not in AMBIGUOUS_CHARACTERS)
            for group in groups
        ]

    if any(not group for group in groups):
        raise ValueError("После исключения символов одна из выбранных групп пуста.")

    special_group = symbols

    if exclude_ambiguous:
        special_group = "".join(
            char for char in special_group if char not in AMBIGUOUS_CHARACTERS
        )

    if min_special > 0 and not special_group:
        raise ValueError("Нет доступных спецсимволов для генерации.")

    # Гарантируем наличие каждого выбранного типа символов.
    password_chars = [secrets.choice(group) for group in groups]

    # Добавляем спецсимволы, если их пока меньше требуемого минимума.
    current_special = sum(char in special_group for char in password_chars)

    while current_special < min_special:
        password_chars.append(secrets.choice(special_group))
        current_special += 1

    if len(password_chars) > length:
        raise ValueError("Для выбранных настроек требуется увеличить длину пароля.")

    all_chars = "".join(groups)

    while len(password_chars) < length:
        password_chars.append(secrets.choice(all_chars))

    secrets.SystemRandom().shuffle(password_chars)

    return "".join(password_chars)


def ask_yes_no(message: str, default: bool = True) -> bool:
    """Запрашивает ответ да или нет."""
    hint = "Д/н" if default else "д/Н"

    while True:
        answer = input(f"{message} ({hint}): ").strip().lower()

        if not answer:
            return default

        if answer in {"д", "да", "y", "yes"}:
            return True

        if answer in {"н", "нет", "n", "no"}:
            return False

        print("Введите д или н.")


def ask_integer(
    message: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Запрашивает целое число в заданном диапазоне."""
    while True:
        raw = input(f"{message} [{default}]: ").strip()

        if not raw:
            return default

        try:
            value = int(raw)
        except ValueError:
            print("Введите целое число.")
            continue

        if minimum <= value <= maximum:
            return value

        print(f"Введите число от {minimum} до {maximum}.")


def generate_with_settings() -> str:
    """Генерирует пароль с настройками, выбранными пользователем."""
    length = ask_integer("Длина пароля (12–64)", 20, 12, 64)

    use_lowercase = ask_yes_no("Использовать строчные буквы?", True)
    use_uppercase = ask_yes_no("Использовать заглавные буквы?", True)
    use_digits = ask_yes_no("Использовать цифры?", True)
    use_symbols = ask_yes_no("Использовать спецсимволы?", True)

    min_special = 0

    if use_symbols:
        min_special = ask_integer(
            "Минимальное количество спецсимволов",
            0,
            0,
            length,
        )

    exclude_ambiguous = ask_yes_no(
        "Исключить похожие символы 0, O, o, l, I, 1?",
        False,
    )

    exclude_uncomfortable = ask_yes_no(
        "Исключить неудобные символы []{};:,.?^?",
        False,
    )

    return generate_password(
        length=length,
        exclude_ambiguous=exclude_ambiguous,
        use_lowercase=use_lowercase,
        use_uppercase=use_uppercase,
        use_digits=use_digits,
        use_symbols=use_symbols,
        min_special=min_special,
        exclude_uncomfortable=exclude_uncomfortable,
    )


# ---------- Работа с учетными записями ----------


def add_entry(
    conn: sqlite3.Connection,
    cipher: Fernet,
    service: str,
    username: str,
    password: str,
) -> None:
    """Сохраняет учетную запись, зашифровывая пароль."""
    service = service.strip()
    username = username.strip()

    if not service or not username or not password:
        raise ValueError("Сервис, логин и пароль не должны быть пустыми.")

    encrypted = cipher.encrypt(password.encode("utf-8"))

    conn.execute(
        """
        INSERT INTO entries (service, username, password_encrypted)
        VALUES (?, ?, ?)
        """,
        (service, username, encrypted),
    )

    conn.commit()


def list_entries(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Возвращает названия сервисов и логины без самих паролей."""
    return conn.execute("""
        SELECT service, username
        FROM entries
        ORDER BY service COLLATE NOCASE
        """).fetchall()


def get_entry(
    conn: sqlite3.Connection,
    cipher: Fernet,
    service: str,
) -> tuple[str, str, str] | None:
    """Находит учетную запись и расшифровывает пароль."""
    row = conn.execute(
        """
        SELECT service, username, password_encrypted
        FROM entries
        WHERE service = ? COLLATE NOCASE
        """,
        (service.strip(),),
    ).fetchone()

    if row is None:
        return None

    password = cipher.decrypt(row[2]).decode("utf-8")

    return row[0], row[1], password


def delete_entry(conn: sqlite3.Connection, service: str) -> bool:
    """Удаляет запись по названию сервиса."""
    cursor = conn.execute(
        "DELETE FROM entries WHERE service = ? COLLATE NOCASE",
        (service.strip(),),
    )

    conn.commit()
    return cursor.rowcount > 0


def create_account(
    conn: sqlite3.Connection,
    cipher: Fernet,
) -> None:
    """Создает учетную запись и сохраняет выбранный пароль."""
    service = input("Название сервиса: ").strip()
    username = input("Логин: ").strip()

    if not service or not username:
        print("Название сервиса и логин обязательны.")
        return

    existing = conn.execute(
        "SELECT 1 FROM entries WHERE service = ? COLLATE NOCASE",
        (service,),
    ).fetchone()

    if existing:
        print(
            "Запись с таким названием уже существует. "
            "Существующая запись не изменена."
        )
        return

    print("\nКак получить пароль?")
    print("1 — Сгенерировать автоматически")
    print("2 — Настроить генерацию")
    print("3 — Ввести собственный пароль")

    choice = input("Ваш выбор (1–3): ").strip()

    if choice == "1":
        password = generate_password()

    elif choice == "2":
        try:
            password = generate_with_settings()
        except ValueError as exc:
            print(f"Не удалось создать пароль: {exc}")
            return

    elif choice == "3":
        password = getpass.getpass("Введите пароль: ")

        if not password:
            print("Пустой пароль сохранить нельзя.")
            return

        confirmation = getpass.getpass("Повторите пароль: ")

        if password != confirmation:
            print("Пароли не совпадают. Запись не сохранена.")
            return

    else:
        print("Неизвестный вариант. Запись не сохранена.")
        return

    print("\nПароль подготовлен.")
    print("Сервис:", service)
    print("Логин:", username)
    print("Пароль:", password)

    if not ask_yes_no("Сохранить эту учетную запись?", True):
        print("Запись не сохранена.")
        return

    try:
        add_entry(conn, cipher, service, username, password)
    except sqlite3.IntegrityError:
        print("Такая запись уже существует. Ничего не перезаписано.")
        return

    print("Учетная запись сохранена. Пароль хранится в зашифрованном виде.")


def generate_without_saving() -> None:
    """Генерирует пароль, не записывая его в базу данных."""
    print("\nГенератор паролей без сохранения")
    print("1 — Быстрая генерация")
    print("2 — Настроить параметры")

    choice = input("Ваш выбор (1–2): ").strip()

    try:
        if choice == "1":
            password = generate_password()
        elif choice == "2":
            password = generate_with_settings()
        else:
            print("Неизвестный вариант.")
            return
    except ValueError as exc:
        print(f"Не удалось создать пароль: {exc}")
        return

    print("\nВаш пароль:")
    print(password)
    print("\nПароль не сохранен в базе данных.")
    print("Скопируйте его, если он вам нужен.")


# ---------- Главное меню ----------


def main() -> int:
    parser = argparse.ArgumentParser(description="Локальный менеджер паролей")
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--key",
        type=Path,
        default=KEY_PATH,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    conn = connect_db(args.db)

    try:
        cipher = get_cipher(args.key)

        if not authenticate(conn):
            return 1

        print("\nМенеджер паролей")
        print("create   — создать учетную запись")
        print("generate — сгенерировать пароль без сохранения")
        print("get      — посмотреть сохраненную запись")
        print("list     — показать список записей")
        print("delete   — удалить запись")
        print("exit     — выйти")

        while True:
            command = input("\nКоманда: ").strip().lower()

            try:
                if command in {"exit", "quit", "q"}:
                    print("До свидания.")
                    return 0

                elif command in {"create", "add"}:
                    create_account(conn, cipher)

                elif command in {"generate", "new"}:
                    generate_without_saving()

                elif command == "list":
                    entries = list_entries(conn)

                    if not entries:
                        print("Сохраненных записей пока нет.")
                    else:
                        for service, username in entries:
                            print(f"- {service}: {username}")

                elif command == "get":
                    service = input("Название сервиса: ").strip()
                    result = get_entry(conn, cipher, service)

                    if result:
                        print(f"Сервис: {result[0]}")
                        print(f"Логин: {result[1]}")
                        print(f"Пароль: {result[2]}")
                    else:
                        print("Запись не найдена.")

                elif command == "delete":
                    service = input("Название сервиса: ").strip()

                    if delete_entry(conn, service):
                        print("Запись удалена.")
                    else:
                        print("Запись не найдена.")

                else:
                    print(
                        "Неизвестная команда. Используйте "
                        "create, generate, get, list, delete или exit."
                    )

            except sqlite3.IntegrityError:
                print("Такая запись уже существует.")
            except (ValueError, InvalidToken) as exc:
                print(f"Не удалось выполнить действие: {exc}")

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

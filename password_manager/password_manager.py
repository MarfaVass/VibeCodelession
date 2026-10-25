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


def connect_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
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
    if not key_path.exists():
        key_path.write_bytes(Fernet.generate_key())
        try:
            key_path.chmod(0o600)
        except OSError:
            pass
    return Fernet(key_path.read_bytes().strip())


def ensure_master_password(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT master_hash FROM settings WHERE id = 1").fetchone()
    if row:
        return
    print("Первый запуск: задайте мастер-пароль (не используйте пароль от другого сервиса).")
    while True:
        master = getpass.getpass("Новый мастер-пароль: ")
        if len(master) < 12:
            print("Используйте не менее 12 символов.")
            continue
        confirm = getpass.getpass("Повторите мастер-пароль: ")
        if master != confirm:
            print("Пароли не совпадают. Попробуйте ещё раз.")
            continue
        # PBKDF2-хэш с солью вместо быстрого SHA-256.
        conn.execute(
            "INSERT INTO settings (id, master_hash) VALUES (1, ?)",
            (generate_password_hash(master, method="pbkdf2:sha256:600000"),),
        )
        conn.commit()
        print("Мастер-пароль сохранён в виде стойкого хэша.")
        return


def authenticate(conn: sqlite3.Connection, attempts: int = 3) -> bool:
    ensure_master_password(conn)
    row = conn.execute("SELECT master_hash FROM settings WHERE id = 1").fetchone()
    for _ in range(attempts):
        candidate = getpass.getpass("Мастер-пароль: ")
        if check_password_hash(row[0], candidate):
            return True
        print("Неверный мастер-пароль.")
    print("Слишком много попыток.")
    return False


def add_entry(conn: sqlite3.Connection, cipher: Fernet, service: str, username: str, password: str) -> None:
    encrypted = cipher.encrypt(password.encode("utf-8"))
    conn.execute(
        "INSERT INTO entries (service, username, password_encrypted) VALUES (?, ?, ?)",
        (service.strip(), username.strip(), encrypted),
    )
    conn.commit()


def list_entries(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    return conn.execute(
        "SELECT service, username FROM entries ORDER BY service COLLATE NOCASE"
    ).fetchall()


def get_entry(conn: sqlite3.Connection, cipher: Fernet, service: str) -> tuple[str, str, str] | None:
    row = conn.execute(
        "SELECT service, username, password_encrypted FROM entries WHERE service = ? COLLATE NOCASE",
        (service.strip(),),
    ).fetchone()
    if row is None:
        return None
    return row[0], row[1], cipher.decrypt(row[2]).decode("utf-8")


def delete_entry(conn: sqlite3.Connection, service: str) -> bool:
    cur = conn.execute("DELETE FROM entries WHERE service = ? COLLATE NOCASE", (service.strip(),))
    conn.commit()
    return cur.rowcount > 0


def generate_password(length: int = 20, exclude_ambiguous: bool = False) -> str:
    if not 12 <= length <= 64:
        raise ValueError("Длина должна быть от 12 до 64 символов.")
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    if exclude_ambiguous:
        chars = chars.translate(str.maketrans("", "", "0OolI1"))
    # Гарантируем хотя бы по одному символу из каждой группы.
    groups = [
        string.ascii_lowercase,
        string.ascii_uppercase,
        string.digits,
        "!@#$%^&*()-_=+",
    ]
    if exclude_ambiguous:
        groups = [g.translate(str.maketrans("", "", "0OolI1")) for g in groups]
    password_chars = [secrets.choice(group) for group in groups]
    password_chars.extend(secrets.choice(chars) for _ in range(length - len(password_chars)))
    secrets.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)


def main() -> int:
    parser = argparse.ArgumentParser(description="Локальный учебный менеджер паролей")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--key", type=Path, default=KEY_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args()

    conn = connect_db(args.db)
    try:
        cipher = get_cipher(args.key)
        if not authenticate(conn):
            return 1
        print("\nМенеджер паролей")
        print("Команды: add, get, list, delete, new, exit")
        while True:
            command = input("\nКоманда: ").strip().lower()
            try:
                if command in {"exit", "quit", "q"}:
                    print("До свидания.")
                    return 0
                elif command == "add":
                    service = input("Сервис/название: ").strip()
                    username = input("Логин: ").strip()
                    if not service or not username:
                        print("Название и логин не могут быть пустыми.")
                        continue
                    password = getpass.getpass("Пароль для сохранения (пусто — сгенерировать): ")
                    if not password:
                        password = generate_password()
                        print(f"Сгенерированный пароль: {password}")
                    add_entry(conn, cipher, service, username, password)
                    print("Запись сохранена.")
                elif command == "get":
                    service = input("Название сервиса: ").strip()
                    result = get_entry(conn, cipher, service)
                    if result:
                        print(f"Сервис: {result[0]}\nЛогин: {result[1]}\nПароль: {result[2]}")
                    else:
                        print("Запись не найдена.")
                elif command == "list":
                    entries = list_entries(conn)
                    if not entries:
                        print("Записей пока нет.")
                    else:
                        for service, username in entries:
                            print(f"- {service}: {username}")
                elif command == "delete":
                    service = input("Название сервиса: ").strip()
                    print("Запись удалена." if delete_entry(conn, service) else "Запись не найдена.")
                elif command == "new":
                    raw_length = input("Длина пароля (12–64, по умолчанию 20): ").strip()
                    length = int(raw_length) if raw_length else 20
                    exclude = input("Исключить похожие символы 0/O, l/I, 1? (д/н): ").strip().lower() in {"д", "да", "y", "yes"}
                    print("Новый пароль:", generate_password(length, exclude))
                else:
                    print("Неизвестная команда. Доступны: add, get, list, delete, new, exit.")
            except sqlite3.IntegrityError:
                print("Запись с таким названием уже существует. Используйте другое название.")
            except (ValueError, InvalidToken) as exc:
                print(f"Не удалось выполнить действие: {exc}")
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

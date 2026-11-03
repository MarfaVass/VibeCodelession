"""Тесты базы данных заявок (SQLite)."""

from __future__ import annotations

import sqlite3

import pytest

from bot.storage import (
    BookingDatabase,
    STATUS_PRELIMINARY,
    STATUS_PROCESSED,
)


def test_database_and_table_created_automatically(tmp_path):
    db_path = tmp_path / "nested" / "bookings.db"
    assert not db_path.parent.exists()
    BookingDatabase(db_path)
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:  # соединение закрыто — читаем отдельно
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "bookings" in tables


def test_save_and_get_booking(db):
    record = db.save_booking(
        vk_id=100500,
        category="specialist",
        name="Анна Петрова",
        contact="+7 900 000-00-01",
        request_text="интересует Matwork 2",
        details={"интересующее направление": "Matwork 2"},
    )
    assert record.id is not None
    loaded = db.get_booking(record.id)
    assert loaded is not None
    assert loaded.vk_id == 100500
    assert loaded.category == "specialist"
    assert loaded.name == "Анна Петрова"
    assert loaded.contact == "+7 900 000-00-01"
    assert loaded.request_text == "интересует Matwork 2"
    assert loaded.details == {"интересующее направление": "Matwork 2"}
    # статус по умолчанию: предварительное обращение
    assert loaded.status == STATUS_PRELIMINARY
    assert loaded.created_at  # дата создания фиксируется


def test_missing_required_field_rejected(db):
    with pytest.raises(ValueError):
        db.save_booking(vk_id=1, category="client", name="", contact="t@e.ru")
    with pytest.raises(ValueError):
        db.save_booking(vk_id=1, category="client", name="Имя", contact="  ")
    with pytest.raises(ValueError):
        db.save_booking(vk_id=1, category="???", name="Имя", contact="t@e.ru")
    assert db.count_bookings() == 0


def test_optional_fields_are_optional(db):
    record = db.save_booking(vk_id=5, category="client", name="Иван", contact="vk.com/id5")
    assert record.request_text == ""
    assert record.details == {}


def test_details_stored_as_json(db):
    db.save_booking(
        vk_id=7,
        category="club",
        name="Ольга",
        contact="mail@club.ru",
        details={"организация": "Fit Life", "сотрудников": "12"},
    )
    loaded = db.get_latest_booking(7)
    assert loaded.details == {"организация": "Fit Life", "сотрудников": "12"}


def test_status_lifecycle(db):
    record = db.save_booking(vk_id=9, category="client", name="Имя", contact="контакт")
    assert db.set_status(record.id, STATUS_PROCESSED)
    assert db.get_booking(record.id).status == STATUS_PROCESSED

    with pytest.raises(ValueError):
        db.set_status(record.id, "weird-status")

    assert not db.set_status(999999, STATUS_PROCESSED)


def test_latest_booking_by_user(db):
    db.save_booking(vk_id=42, category="client", name="Первая", contact="a")
    second = db.save_booking(vk_id=42, category="client", name="Вторая", contact="b")
    db.save_booking(vk_id=43, category="client", name="Другой", contact="c")
    assert db.get_latest_booking(42).id == second.id
    assert db.get_latest_booking(999) is None
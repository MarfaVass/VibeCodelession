"""Утилиты для работы с датами и временем.

В базе данных все моменты времени хранятся в UTC в ISO-формате
('YYYY-MM-DDTHH:MM:SS'). Для отображения пользователю время
конвертируется в часовой пояс из настройки TIMEZONE.
"""

from __future__ import annotations

import zoneinfo
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc


def now_utc() -> datetime:
    """Текущий момент времени в UTC."""
    return datetime.now(tz=UTC)


def now_utc_iso() -> str:
    """Текущий момент в UTC как строка ISO для записи в БД."""
    return now_utc().isoformat(timespec="seconds")


def get_local_tz(timezone_name: str) -> zoneinfo.ZoneInfo:
    """Возвращает объект часового пояса по названию (например 'Europe/Stockholm').

    При неизвестном поясе безопасно возвращаем UTC, чтобы бот не падал.
    """
    try:
        return zoneinfo.ZoneInfo(timezone_name)
    except zoneinfo.ZoneInfoNotFoundError:
        return zoneinfo.ZoneInfo("UTC")


def utc_to_local(iso_utc: str | None, timezone_name: str) -> datetime | None:
    """Конвертирует ISO-строку UTC в datetime в локальном поясе."""
    if not iso_utc:
        return None
    dt = datetime.fromisoformat(iso_utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(get_local_tz(timezone_name))


def format_datetime(iso_utc: str | None, timezone_name: str) -> str:
    """Форматирует момент времени для показа пользователю: '19.11.2026 14:30'."""
    local = utc_to_local(iso_utc, timezone_name)
    if local is None:
        return "—"
    return local.strftime("%d.%m.%Y %H:%M")


def format_date(iso_utc: str | None, timezone_name: str) -> str:
    """Форматирует только дату: '19.11.2026'."""
    local = utc_to_local(iso_utc, timezone_name)
    if local is None:
        return "—"
    return local.strftime("%d.%m.%Y")


def parse_deadline(text: str, timezone_name: str) -> date | None:
    """Разбирает пользовательский ввод дедлайна.

    Поддерживает форматы: '2026-11-25', '25.11.2026', '25.11.26',
    а также слова 'сегодня', 'завтра', 'послезавтра'.

    Возвращает date в локальном поясе или None, если разобрать не удалось.
    """
    text = text.strip().lower()
    today = datetime.now(tz=get_local_tz(timezone_name)).date()

    simple_words = {
        "сегодня": today,
        "завтра": today + timedelta(days=1),
        "послезавтра": today + timedelta(days=2),
    }
    if text in simple_words:
        return simple_words[text]

    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            # Для формата без года подставляем текущий год.
            if "%y" not in fmt and "%Y" not in fmt:
                parsed = parsed.replace(year=today.year)
            return parsed
        except ValueError:
            continue
    return None


def deadline_iso(due_date: date) -> str:
    """Дедлайн хранится как конец local-day, переведённый в UTC.

    Так «просрочено» считается корректно: дедлайн 19.11 в поясе Stockholm
    наступает в 23:59 местного времени, что соответствует раннему
    утру 19.11 UTC.
    """
    return deadline_to_iso(due_date, "UTC")


def deadline_to_iso(due_date: date, timezone_name: str) -> str:
    """Преобразует дату дедлайна в ISO-строку UTC (конец дня по местному времени)."""
    tz = get_local_tz(timezone_name)
    end_of_day = datetime(
        due_date.year, due_date.month, due_date.day, 23, 59, 59, tzinfo=tz
    )
    return end_of_day.astimezone(UTC).isoformat(timespec="seconds")


def is_overdue(due_date_iso: str | None, status_is_final: bool = False,
               timezone_name: str = "UTC") -> bool:
    """Задача просрочена, если дедлайн в прошлом и задача ещё не завершена."""
    if not due_date_iso or status_is_final:
        return False
    tz = get_local_tz(timezone_name)
    deadline = datetime.fromisoformat(due_date_iso)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    return deadline < datetime.now(tz=UTC)

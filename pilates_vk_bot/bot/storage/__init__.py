"""Хранение предварительных заявок (SQLite)."""

from .db import (
    BookingDatabase,
    BookingRecord,
    CATEGORIES,
    STATUS_CANCELLED,
    STATUS_PRELIMINARY,
    STATUS_PROCESSED,
)

__all__ = [
    "BookingDatabase",
    "BookingRecord",
    "CATEGORIES",
    "STATUS_CANCELLED",
    "STATUS_PRELIMINARY",
    "STATUS_PROCESSED",
]
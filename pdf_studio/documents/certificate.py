"""Сценарий «Сертификат»: валидация полей формы и генерация PDF.

Модуль не зависит от Tkinter — GUI только собирает данные, здесь
проходит вся валидация, подстановка значений по умолчанию и создание PDF.
"""

import random
from datetime import date
from pathlib import Path

from common import pdf_output
from common.validation import clean_text, parse_date_ru

# Подставляется, если пользователь оставил организацию пустой.
DEFAULT_ORG = "Курс вайб-кодирования"


def generate_certificate_number(cert_date: date) -> str:
    """Номер вида PS-ГГГГММДД-NNNN: дата сертификата + случайный серийник.

    Дата берется не «сегодня», а та, что стоит в поле «Дата сертификата»,
    поэтому номер согласован с датой на документе.
    """
    return f"PS-{cert_date:%Y%m%d}-{random.randint(0, 9999):04d}"


def validate_certificate(data: dict) -> dict:
    """Проверяет поля формы сертификата и готовит контекст для шаблона.

    Обязательные поля: имя получателя и название курса/мероприятия/
    номинации. Дата пустым значением заменяется сегодняшней; организация
    и номер не обязательны и подставляются автоматически.
    Возбуждает DataError с понятным сообщением при некорректных данных.
    """
    recipient = clean_text(data.get("recipient"), "имя получателя")
    occasion = clean_text(
        data.get("occasion"),
        "название курса, мероприятия или номинации",
    )
    cert_date = parse_date_ru(data.get("date"), "дата сертификата")
    org = clean_text(
        data.get("org"), "организация или автор", required=False
    ) or DEFAULT_ORG
    number = clean_text(
        data.get("number"), "номер сертификата", required=False
    ) or generate_certificate_number(cert_date)

    return {
        "recipient": recipient,
        "occasion": occasion,
        "cert_date": cert_date.strftime("%d.%m.%Y"),
        "org": org,
        "number": number,
    }


def create_certificate_pdf(data: dict) -> Path:
    """Создает PDF-сертификат из полей формы и возвращает путь к файлу."""
    context = validate_certificate(data)
    return pdf_output.render_and_save("certificate.html", context, "certificate")
"""Тесты PDF Studio (этап 1): валидация сертификата, номера и генерация PDF.

Тесты не используют Tkinter — проверяется бизнес-логика documents/.
Запуск (PowerShell, из корня репозитория):
    .\\venv\\Scripts\\python.exe -m unittest discover pdf_studio\\tests
"""

import re
import sys
import unittest
from datetime import date
from pathlib import Path

_STUDIO_DIR = Path(__file__).resolve().parents[1]
if str(_STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(_STUDIO_DIR))

from common.errors import DataError  # noqa: E402
from documents import certificate  # noqa: E402

FIXED_DATE = date(2026, 10, 28)


def field_error(**overrides) -> str:
    """Собирает данные с одним некорректным полем и возвращает текст ошибки."""
    data = {
        "recipient": "Анна Смирнова",
        "occasion": "Клавиатурный подвиг",
        "date": FIXED_DATE.strftime("%d.%m.%Y"),
        "org": "",
        "number": "",
    }
    data.update(overrides)
    try:
        certificate.validate_certificate(data)
    except DataError as error:
        return str(error)
    return ""


class CertificateValidationTests(unittest.TestCase):
    """Валидация полей формы сертификата."""

    def test_recipient_required(self):
        error = field_error(recipient="   ")
        self.assertIn("имя получателя", error)

    def test_occasion_required(self):
        error = field_error(occasion="")
        self.assertIn("название курса", error)

    def test_recipient_too_long(self):
        error = field_error(recipient="И" * 121)
        self.assertIn("слишком длинное", error)

    def test_recipient_trims_whitespace(self):
        context = certificate.validate_certificate(
            {"recipient": "  Анна Смирнова  ", "occasion": "Номинация",
             "date": "28.10.2026"}
        )
        self.assertEqual(context["recipient"], "Анна Смирнова")

    def test_date_valid(self):
        context = certificate.validate_certificate(
            {"recipient": "А", "occasion": "Б", "date": "05.03.2026"}
        )
        self.assertEqual(context["cert_date"], "05.03.2026")

    def test_date_invalid_day(self):
        error = field_error(date="31.02.2026")
        self.assertIn("не корректная дата", error)

    def test_date_wrong_format(self):
        error = field_error(date="2026-10-28")
        self.assertIn("не корректная дата", error)

    def test_date_empty_defaults_to_today(self):
        context = certificate.validate_certificate(
            {"recipient": "Анна", "occasion": "Номинация", "date": ""}
        )
        today = date.today().strftime("%d.%m.%Y")
        self.assertEqual(context["cert_date"], today)

    def test_org_default(self):
        context = certificate.validate_certificate(
            {"recipient": "Анна", "occasion": "Номинация"}
        )
        self.assertEqual(context["org"], certificate.DEFAULT_ORG)

    def test_org_custom(self):
        context = certificate.validate_certificate(
            {"recipient": "Анна", "occasion": "Номинация",
             "org": "  Школа тестов  "}
        )
        self.assertEqual(context["org"], "Школа тестов")


class CertificateNumberTests(unittest.TestCase):
    """Генерация номера сертификата."""

    def test_generated_format(self):
        number = certificate.generate_certificate_number(FIXED_DATE)
        self.assertRegex(number, r"^PS-\d{8}-\d{4}$")

    def test_generated_embeds_date(self):
        number = certificate.generate_certificate_number(FIXED_DATE)
        self.assertTrue(number.startswith("PS-20261028-"), number)

    def test_generated_serial_in_range(self):
        for _ in range(20):
            number = certificate.generate_certificate_number(FIXED_DATE)
            serial = int(number.rsplit("-", 1)[1])
            self.assertGreaterEqual(serial, 0)
            self.assertLessEqual(serial, 9999)

    def test_explicit_number_preserved(self):
        context = certificate.validate_certificate(
            {"recipient": "Анна", "occasion": "Номинация",
             "number": "  TEST-001  "}
        )
        self.assertEqual(context["number"], "TEST-001")

    def test_empty_number_generated(self):
        context = certificate.validate_certificate(
            {"recipient": "Анна", "occasion": "Номинация", "number": "",
             "date": "28.10.2026"}
        )
        self.assertRegex(context["number"], r"^PS-20261028-\d{4}$")


class CertificatePdfGenerationTests(unittest.TestCase):
    """Интеграционная генерация PDF (weasyprint должен быть установлен)."""

    def test_two_pdfs_do_not_overwrite_each_other(self):
        first = certificate.create_certificate_pdf(
            {"recipient": "Анна Смирнова",
             "occasion": "Клавиатурный подвиг: 100% покрытие тестами",
             "date": "28.10.2026"}
        )
        second = certificate.create_certificate_pdf(
            {"recipient": "Анна Смирнова",
             "occasion": "Клавиатурный подвиг: 100% покрытие тестами",
             "date": "28.10.2026"}
        )
        self.assertNotEqual(first, second)
        for path in (first, second):
            self.assertTrue(path.is_file(), path)
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"%PDF"), path)
            self.assertGreater(len(raw), 3000, path)
        self.assertIn("certificate_", first.name)

    def test_template_render_contains_fields(self):
        """Шаблон реально подставляет все поля (содержимое HTML)."""
        import jinja2

        from common.paths import TEMPLATE_DIR

        context = certificate.validate_certificate(
            {"recipient": "Тест Тестов", "occasion": "Номинация для проверки",
             "date": "28.10.2026", "org": "Организация", "number": "N-1"}
        )
        environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=jinja2.select_autoescape(["html"]),
        )
        html = environment.get_template("certificate.html").render(**context)
        # Текст сравниваем с нормализованными пробелами: разметка и переносы
        # строк в шаблоне не должны влиять на проверку содержимого.
        flat = " ".join(html.split())
        for value in ("Тест Тестов", "Номинация для проверки",
                      "Организация", "N-1", "СЕРТИФИКАТ",
                      "не является документом об образовании"):
            self.assertIn(value, flat)


if __name__ == "__main__":
    unittest.main()
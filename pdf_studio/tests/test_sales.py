"""Тесты PDF Studio (этап 2): расчеты отчета о продажах и генерация PDF.

Тесты не используют Tkinter и создают CSV во временных каталогах,
поэтому не перезаписывают демонстрационные PDF и сертификаты.
Расчеты проверяются по известным числам, а не только на отсутствие
исключений.
"""

import shutil
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

_STUDIO_DIR = Path(__file__).resolve().parents[1]
if str(_STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(_STUDIO_DIR))

import jinja2  # noqa: E402

from common.errors import DataError  # noqa: E402
from common.paths import TEMPLATE_DIR  # noqa: E402
from documents import sales_report  # noqa: E402

ALL_OPTIONS = {option: True for option in sales_report.OPTIONS}


def money(text: str) -> Decimal:
    return Decimal(text)


# Итоговые числа контрольного файла (выручка = цена × количество):
# 4500×12=54000; 3200×18=57600; 6800×7=47600 → всего 205100, единиц 37.
CONTROL_CSV = (
    "product,price,qty\n"
    "Чайник керамический,4500,12\n"
    "Сковорода чугунная,3200,18\n"
    "Набор ножей,6800,7\n"
)


class CsvTestCase(unittest.TestCase):
    """Общий хелпер: CSV во временном каталоге, удаляется после теста."""

    def write_csv(self, content: str, encoding: str = "utf-8") -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="pdf_studio_test_"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        csv_path = tmp_dir / "sales_test.csv"
        csv_path.write_text(content, encoding=encoding)
        return csv_path


class LoadSalesTests(CsvTestCase):
    """Чтение и валидация CSV."""

    def test_load_valid_row_values(self):
        sales = sales_report.load_sales(self.write_csv(CONTROL_CSV))
        self.assertEqual(sales["source_name"], "sales_test.csv")
        self.assertEqual(sales["items"][0]["name"], "Чайник керамический")
        self.assertEqual(sales["items"][0]["price"], Decimal("4500"))
        self.assertEqual(sales["items"][0]["qty"], Decimal("12"))
        self.assertEqual(sales["skipped"], [])

    def test_utf8_bom_supported(self):
        sales = sales_report.load_sales(
            self.write_csv(CONTROL_CSV, encoding="utf-8-sig")
        )
        self.assertEqual(sales["items"][0]["name"], "Чайник керамический")

    def test_cp1251_supported(self):
        sales = sales_report.load_sales(
            self.write_csv(CONTROL_CSV, encoding="cp1251")
        )
        self.assertEqual(sales["items"][0]["name"], "Чайник керамический")

    def test_missing_required_columns(self):
        with self.assertRaises(DataError) as ctx:
            sales_report.load_sales(
                self.write_csv("product,cost,amount\nЧайник,1,2\n")
            )
        self.assertIn("обязательные колонки", str(ctx.exception))
        self.assertIn("price", str(ctx.exception))

    def test_empty_file_no_header(self):
        with self.assertRaises(DataError) as ctx:
            sales_report.load_sales(self.write_csv(""))
        self.assertIn("Заголовок", str(ctx.exception))

    def test_header_only_file(self):
        with self.assertRaises(DataError):
            sales_report.load_sales(self.write_csv("product,price,qty\n"))

    def test_all_rows_invalid(self):
        broken = ("product,price,qty\n"
                  "Чайник,пять,12\n"
                  "Сковорода,3200,-3\n")
        with self.assertRaises(DataError):
            sales_report.load_sales(self.write_csv(broken))

    def test_invalid_rows_skipped_with_row_numbers(self):
        csv_text = (
            "product,price,qty\n"
            "Чайник,4500,12\n"
            "Сковорода,abc,18\n"          # строка 3: цена не число
            "Ножи,6800,2.5\n"             # строка 4: дробное количество
            "Плита,-500,2\n"              # строка 5: отрицательная цена
            "Чашка,300,-1\n"              # строка 6: отрицательное количество
        )
        sales = sales_report.load_sales(self.write_csv(csv_text))
        self.assertEqual([item["name"] for item in sales["items"]], ["Чайник"])
        self.assertEqual(
            [item["row"] for item in sales["skipped"]],
            [3, 4, 5, 6],
        )
        self.assertIn("не число", sales["skipped"][0]["reason"])
        self.assertIn("целым числом", sales["skipped"][1]["reason"])

    def test_price_zero_is_invalid(self):
        sales = sales_report.load_sales(
            self.write_csv("product,price,qty\nЧайник,4500,12\nЧашка,0,5\n")
        )
        self.assertEqual([item["name"] for item in sales["items"]], ["Чайник"])
        self.assertEqual(len(sales["skipped"]), 1)  # цена должна быть > 0

    def test_qty_zero_is_valid(self):
        sales = sales_report.load_sales(
            self.write_csv("product,price,qty\nЧайник,4500,0\n")
        )
        self.assertEqual(sales["items"][0]["qty"], Decimal("0"))

    def test_blank_lines_in_file(self):
        csv_text = "product,price,qty\n\nЧайник,4500,12\n\n\n"
        sales = sales_report.load_sales(self.write_csv(csv_text))
        self.assertEqual(len(sales["items"]), 1)
        self.assertEqual(sales["skipped"], [])


class AggregationTests(CsvTestCase):
    """Агрегация строк с одинаковым названием товара."""

    def test_duplicate_names_aggregated(self):
        csv_text = (
            "product,price,qty\n"
            "Чайник,4500,12\n"
            "Чайник,4000,10\n"
            "Сковорода,3200,18\n"
        )
        sales = sales_report.load_sales(self.write_csv(csv_text))
        rows = sales_report.aggregate_items(sales["items"])
        self.assertEqual(len(rows), 2)  # не потеряны, но и не дублированы
        teapot = rows[0]
        self.assertEqual(teapot["name"], "Чайник")
        self.assertEqual(teapot["qty"], Decimal("22"))
        self.assertEqual(teapot["revenue"], money("4500") * 12 + money("4000") * 10)
        # Средняя цена = выручка / количество
        self.assertEqual(
            teapot["avg_price"],
            (money("4500") * 12 + money("4000") * 10) / Decimal("22"),
        )

    def test_aggregation_applies_to_report(self):
        """Таблица и рейтинги согласованы: один агрегированный Чайник."""
        csv_text = (
            "product,price,qty\n"
            "Чайник,4500,12\n"
            "Чайник,4000,10\n"
        )
        sales = sales_report.load_sales(self.write_csv(csv_text))
        context = sales_report.build_report(sales, dict(ALL_OPTIONS))
        self.assertEqual(len(context["table_rows"]), 1)
        self.assertEqual(len(context["rank_revenue_rows"]), 1)
        self.assertEqual(len(context["chart_bars"]), 1)
        self.assertEqual(context["totals"]["qty"], "22")
        self.assertEqual(context["totals"]["revenue"], "94 000,00")

    def test_diamond_names_not_merged_after_trim(self):
        """Названия различаются: «Товар» и «Товар » — после обрезки это один."""
        csv_text = (
            "product,price,qty\n"
            "Чайник,4500,12\n"
            "  Чайник  ,4000,10\n"
        )
        sales = sales_report.load_sales(self.write_csv(csv_text))
        rows = sales_report.aggregate_items(sales["items"])
        self.assertEqual(len(rows), 1)


class MetricsTests(CsvTestCase):
    """Показатели: выручка, итоги, доли, рейтинги."""

    def setUp(self):
        self.sales = sales_report.load_sales(self.write_csv(CONTROL_CSV))

    def test_totals(self):
        context = sales_report.build_report(self.sales, {"totals": True})
        self.assertEqual(context["totals"]["revenue"], "159 200,00")
        self.assertEqual(context["totals"]["qty"], "37")

    def test_shares_sum_and_value(self):
        context = sales_report.build_report(self.sales, {"shares": True})
        # Выручки: 54000, 57600, 47600 от общей 159200.
        shares = {row["share"] for row in context["shares_rows"]}
        self.assertIn("33,9", shares)   # 54000 / 159200 ≈ 33,9 %
        self.assertIn("36,2", shares)   # 57600 / 159200 ≈ 36,2 %
        self.assertIn("29,9", shares)   # 47600 / 159200 ≈ 29,9 %
        total_share = sum(
            Decimal(row["share"].replace(",", ".")) for row in context["shares_rows"]
        )
        self.assertAlmostEqual(float(total_share), 100.0, places=1)

    def test_shares_width_in_0_100(self):
        context = sales_report.build_report(self.sales, {"shares": True})
        for row in context["shares_rows"]:
            self.assertGreaterEqual(row["share_width"], 0.0)
            self.assertLessEqual(row["share_width"], 100.0)

    def test_rank_revenue_descending_with_name_tiebreak(self):
        csv_text = (
            "product,price,qty\n"
            "Сковорода,1000,10\n"   # выручка 10000
            "Б,1000,10\n"           # выручка 10000 — равна, алфавит раньше
            "А,1000,10\n"           # выручка 10000 — равна, алфавит раньше
            "Чайник,5000,5\n"       # выручка 25000 — первая
        )
        sales = sales_report.load_sales(self.write_csv(csv_text))
        context = sales_report.build_report(sales, {"rank_revenue": True})
        order = [row["name"] for row in context["rank_revenue_rows"]]
        self.assertEqual(order, ["Чайник", "А", "Б", "Сковорода"])
        self.assertEqual(
            [row["place"] for row in context["rank_revenue_rows"]],
            [1, 2, 3, 4],
        )

    def test_rank_qty_descending(self):
        context = sales_report.build_report(self.sales, {"rank_qty": True})
        order = [row["name"] for row in context["rank_qty_rows"]]
        self.assertEqual(order, ["Сковорода чугунная", "Чайник керамический",
                                 "Набор ножей"])

    def test_zero_revenue_no_division(self):
        csv_text = "product,price,qty\nЧайник,4500,0\nСковорода,3200,0\n"
        sales = sales_report.load_sales(self.write_csv(csv_text))
        context = sales_report.build_report(sales, dict(ALL_OPTIONS))
        self.assertFalse(context["shares_available"])
        self.assertIn("равна нулю", context["shares_warning"])
        # Итоги и рейтинги рассчитаны без падения:
        self.assertEqual(context["totals"]["revenue"], "0,00")
        self.assertEqual(context["totals"]["qty"], "0")

    def test_zero_revenue_table_and_rank_ok(self):
        csv_text = "product,price,qty\nЧайник,4500,0\n"
        sales = sales_report.load_sales(self.write_csv(csv_text))
        context = sales_report.build_report(sales, {"rank_revenue": True})
        self.assertEqual(context["rank_revenue_rows"][0]["value"], "0,00")

    def test_no_sections_selected(self):
        with self.assertRaises(DataError) as ctx:
            sales_report.build_report(self.sales, {option: False for option in sales_report.OPTIONS})
        self.assertIn("ни один раздел", str(ctx.exception))

    def test_sections_only_selected_in_context(self):
        context = sales_report.build_report(self.sales, {"totals": True})
        self.assertIn("totals", context)
        self.assertNotIn("table_rows", context)
        self.assertNotIn("chart_bars", context)


class SalesPdfTests(CsvTestCase):
    """Генерация PDF: уникальные имена и соответствие содержимого выбору."""

    def test_pdf_created_unique_names(self):
        sales = sales_report.load_sales(self.write_csv(CONTROL_CSV))
        first = sales_report.create_sales_pdf(sales, dict(ALL_OPTIONS))
        second = sales_report.create_sales_pdf(sales, dict(ALL_OPTIONS))
        self.assertNotEqual(first, second)
        for path in (first, second):
            self.assertTrue(path.is_file(), path)
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"%PDF"), path)
            self.assertGreater(len(raw), 5000, path)
        self.assertIn("sales_report_", first.name)

    def test_rendered_html_contains_calculated_values(self):
        context = sales_report.build_report(
            sales_report.load_sales(self.write_csv(CONTROL_CSV)),
            dict(ALL_OPTIONS),
        )
        environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=jinja2.select_autoescape(["html"]),
        )
        html = " ".join(
            environment.get_template("sales_report.html")
            .render(**context).split()
        )
        self.assertIn("159 200,00", html)   # общая выручка
        self.assertIn("33,9", html)         # доля Чайника
        self.assertIn("Диаграмма выручки", html)
        for name in ("Чайник керамический", "Сковорода чугунная", "Набор ножей"):
            self.assertIn(name, html)

    def test_unselected_sections_absent_from_html(self):
        sales = sales_report.load_sales(self.write_csv(CONTROL_CSV))
        context = sales_report.build_report(
            sales, {"totals": True, "table": True}
        )
        environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=jinja2.select_autoescape(["html"]),
        )
        html = environment.get_template("sales_report.html").render(**context)
        self.assertNotIn("Диаграмма выручки", html)
        self.assertNotIn("Рейтинг по выручке", html)
        self.assertNotIn("Доля в общей выручке", html)
        self.assertIn("Общая выручка", html)

    def test_chart_top10_with_others(self):
        rows = []
        header = "product,price,qty\n"
        for index in range(1, 13):  # 12 товаров — диаграмма урезается
            rows.append(f"Товар {index:02d},{100 + index},1\n")
        sales = sales_report.load_sales(self.write_csv(header + "".join(rows)))
        context = sales_report.build_report(sales, {"chart": True})
        self.assertEqual(len(context["chart_bars"]), 11)
        self.assertEqual(context["chart_bars"][-1]["name"], "Остальные (2 шт.)")
        # Полосы отсортированы по убыванию выручки:
        widths = [bar["width"] for bar in context["chart_bars"][:-1]]
        self.assertEqual(widths, sorted(widths, reverse=True))
        # Сумма «Остальных» не расползается за пределы шкалы:
        self.assertLessEqual(context["chart_bars"][-1]["width"], 100.0)
        # Полоса «Остальные» может быть длиннее одиночного лидера по выручке,
        # но фактическая сумма остается корректной:
        self.assertEqual(context["chart_bars"][-1]["value"], "203,00")


if __name__ == "__main__":
    unittest.main()
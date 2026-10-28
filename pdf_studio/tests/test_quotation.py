"""Тесты PDF Studio (этап 3): коммерческое предложение.

Проверяются конкретные числовые результаты расчетов, фильтрация,
скидки и содержимое HTML перед рендерингом. Каталоги создаются во
временных папках; рабочие документы не перезаписываются.
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
from documents import quotation  # noqa: E402

ALL_CATEGORIES = quotation.ALL_CATEGORIES

VALID_CATALOGUE = (
    'sku,name,category,price,description\n'
    'IR-001,"Утюг паровой HomePro 2400",Утюги,4590,"Керамическая подошва"\n'
    'IR-002,"Утюг компактный Travel",Утюги,2190,"Для поездок"\n'
    'WM-001,"Стиральная машина Aqua 7",Стиральные машины,38990,"Загрузка 7 кг"\n'
)


class CatalogueTestCase(unittest.TestCase):
    """Общий хелпер: CSV во временном каталоге, удаляется после теста."""

    def write_csv(self, content: str, encoding: str = "utf-8") -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="pdf_studio_test_"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        csv_path = tmp_dir / "catalogue_test.csv"
        csv_path.write_text(content, encoding=encoding)
        return csv_path

    def write_valid_catalogue(self, **kwargs) -> Path:
        return self.write_csv(VALID_CATALOGUE, **kwargs)


class CatalogueLoadTests(CatalogueTestCase):
    """Чтение и валидация каталога."""

    def test_load_valid_catalogue(self):
        catalogue = quotation.load_catalogue(self.write_valid_catalogue())
        self.assertEqual(catalogue["source_name"], "catalogue_test.csv")
        self.assertEqual(len(catalogue["items"]), 3)
        first = catalogue["items"][0]
        self.assertEqual(first["sku"], "IR-001")
        self.assertEqual(first["name"], "Утюг паровой HomePro 2400")
        self.assertEqual(first["price"], Decimal("4590"))
        self.assertEqual(first["description"], "Керамическая подошва")

    def test_commas_inside_quotes(self):
        catalogue = quotation.load_catalogue(self.write_valid_catalogue())
        second = catalogue["items"][1]
        self.assertEqual(second["name"], "Утюг компактный Travel")
        third = catalogue["items"][2]
        self.assertEqual(third["description"], "Загрузка 7 кг")

    def test_utf8_bom_supported(self):
        catalogue = quotation.load_catalogue(
            self.write_valid_catalogue(encoding="utf-8-sig")
        )
        self.assertEqual(catalogue["items"][0]["name"],
                         "Утюг паровой HomePro 2400")

    def test_cp1251_supported(self):
        catalogue = quotation.load_catalogue(
            self.write_valid_catalogue(encoding="cp1251")
        )
        self.assertEqual(catalogue["items"][0]["name"],
                         "Утюг паровой HomePro 2400")

    def test_missing_required_columns(self):
        with self.assertRaises(DataError) as ctx:
            quotation.load_catalogue(
                self.write_csv("sku,name,price\nIR-001,Утюг,4590\n")
            )
        self.assertIn("category", str(ctx.exception))

    def test_empty_catalogue(self):
        with self.assertRaises(DataError):
            quotation.load_catalogue(self.write_csv("sku,name,category,price\n"))

    def test_invalid_price_skipped_with_row(self):
        catalogue = quotation.load_catalogue(self.write_csv(
            "sku,name,category,price\n"
            "IR-001,Утюг,Утюги,4590\n"
            "IR-002,Утюг 2,Утюги,-100\n"
            "IR-003,Утюг 3,Утюги,дорого\n"
        ))
        self.assertEqual([item["sku"] for item in catalogue["items"]], ["IR-001"])
        self.assertEqual([item["row"] for item in catalogue["skipped"]][0], 3)

    def test_duplicate_sku_identical_data_deduped(self):
        catalogue = quotation.load_catalogue(self.write_csv(
            "sku,name,category,price\n"
            "IR-001,Утюг HomePro,Утюги,4590\n"
            "IR-001,Утюг HomePro,Утюги,4590\n"
        ))
        self.assertEqual(len(catalogue["items"]), 1)
        self.assertEqual(len(catalogue["skipped"]), 1)

    def test_duplicate_sku_contradictory_data_rejected(self):
        with self.assertRaises(DataError) as ctx:
            quotation.load_catalogue(self.write_csv(
                "sku,name,category,price\n"
                "IR-001,Утюг HomePro,Утюги,4590\n"
                "IR-001,Утюг Другой,Утюги,4590\n"
            ))
        self.assertIn("IR-001", str(ctx.exception))
        self.assertIn("повторно", str(ctx.exception))


class CategoryAndFilterTests(CatalogueTestCase):
    """Категории из данных и фильтрация."""

    def setUp(self):
        self.catalogue = quotation.load_catalogue(
            self.write_csv(VALID_CATALOGUE + (
                'BR-001,"Гладильная доска Comfort",Гладильные доски,6490,"Высота"\n'
                'AC-001,Отпариватель напольный,Аксессуары,5990,"1800 Вт"\n'
            ))
        )

    def test_categories_from_data_sorted(self):
        self.assertEqual(
            quotation.get_categories(self.catalogue),
            ["Аксессуары", "Гладильные доски", "Стиральные машины", "Утюги"],
        )

    def test_filter_by_category(self):
        irons = quotation.filter_items(self.catalogue, "Утюги")
        self.assertEqual([item["sku"] for item in irons], ["IR-001", "IR-002"])

    def test_filter_all_categories(self):
        everything = quotation.filter_items(self.catalogue, ALL_CATEGORIES)
        self.assertEqual(len(everything), 5)

    def test_filter_without_category(self):
        everything = quotation.filter_items(self.catalogue, None)
        self.assertEqual(len(everything), 5)

    def test_search_by_sku_case_insensitive(self):
        found = quotation.filter_items(self.catalogue, search="wm")
        self.assertEqual([item["sku"] for item in found], ["WM-001"])

    def test_search_by_name_substring(self):
        found = quotation.filter_items(self.catalogue, search="машина")
        self.assertEqual([item["sku"] for item in found], ["WM-001"])

    def test_search_and_category_combined(self):
        found = quotation.filter_items(self.catalogue, "Утюги", search="travel")
        self.assertEqual([item["sku"] for item in found], ["IR-002"])
        nothing = quotation.filter_items(self.catalogue, "Утюги", search="Aqua")
        self.assertEqual(nothing, [])


class QuotationCalcTests(CatalogueTestCase):
    """Расчеты: позиции, скидки, итоги (Decimal)."""

    def setUp(self):
        self.catalogue = quotation.load_catalogue(
            self.write_csv(VALID_CATALOGUE + (
                'AC-001,Отпариватель напольный,Аксессуары,19.99,"Дробная цена"\n'
            ))
        )

    def test_line_sum(self):
        calc = quotation.calculate_quotation(
            self.catalogue, [{"sku": "IR-001", "qty": "3"}], "0"
        )
        self.assertEqual(calc["rows"][0]["line_sum"], Decimal("13770.00"))

    def test_subtotal(self):
        calc = quotation.calculate_quotation(self.catalogue, [
            {"sku": "IR-001", "qty": "3"},
            {"sku": "IR-002", "qty": "2"},
        ], "0")
        self.assertEqual(calc["subtotal"], Decimal("13770.00") + Decimal("4380.00"))

    def test_discount_percent_and_grand_total(self):
        # 59,97 − 15 %: скидка 8,9955 → 9,00 (вверх); итог 50,97.
        calc = quotation.calculate_quotation(
            self.catalogue, [{"sku": "AC-001", "qty": "3"}], "15"
        )
        self.assertEqual(calc["discount_amount"], Decimal("9.00"))
        self.assertEqual(calc["grand_total"], Decimal("50.97"))
        self.assertEqual(calc["subtotal"], Decimal("59.97"))

    def test_discount_up_rule(self):
        # 100.05 × 15 % = 15.0075 → 15.01; итог 100.05 − 15.01 = 85.04.
        catalogue = quotation.load_catalogue(self.write_csv(
            "sku,name,category,price\nAC-002,Тест,Тесты,100.05\n"
        ))
        calc = quotation.calculate_quotation(
            catalogue, [{"sku": "AC-002", "qty": 1}], "15"
        )
        self.assertEqual(calc["discount_amount"], Decimal("15.01"))
        self.assertEqual(calc["grand_total"], Decimal("85.04"))

    def test_discount_zero_not_in_context(self):
        """При скидке 0 % декоративной строки «Скидка» в контексте нет."""
        calc = quotation.calculate_quotation(
            self.catalogue, [{"sku": "IR-001", "qty": "1"}], "0"
        )
        self.assertEqual(calc["discount_pct"], Decimal("0"))
        context = quotation.build_context(
            self.catalogue, [{"sku": "IR-001", "qty": "1"}], "0"
        )
        self.assertFalse(context["has_discount"])

    def test_discount_90_boundary(self):
        calc = quotation.calculate_quotation(
            self.catalogue, [{"sku": "IR-001", "qty": "10"}], "90"
        )
        # 4590 × 10 = 45900; скидка 90 % = 41310; итог 4590.
        self.assertEqual(calc["subtotal"], Decimal("45900.00"))
        self.assertEqual(calc["grand_total"], Decimal("4590.00"))

    def test_discount_negative_rejected(self):
        with self.assertRaises(DataError) as ctx:
            quotation.calculate_quotation(
                self.catalogue, [{"sku": "IR-001", "qty": "1"}], "-1"
            )
        self.assertIn("отрицательной", str(ctx.exception))

    def test_discount_above_90_rejected(self):
        with self.assertRaises(DataError):
            quotation.calculate_quotation(
                self.catalogue, [{"sku": "IR-001", "qty": "1"}], "91"
            )

    def test_discount_not_a_number_rejected(self):
        with self.assertRaises(DataError):
            quotation.calculate_quotation(
                self.catalogue, [{"sku": "IR-001", "qty": "1"}], "двадцать"
            )

    def test_qty_zero_rejected(self):
        with self.assertRaises(DataError) as ctx:
            quotation.calculate_quotation(
                self.catalogue, [{"sku": "IR-001", "qty": "0"}]
            )
        self.assertIn("не меньше 1", str(ctx.exception))

    def test_qty_negative_rejected(self):
        with self.assertRaises(DataError):
            quotation.calculate_quotation(
                self.catalogue, [{"sku": "IR-001", "qty": "-2"}]
            )

    def test_qty_frac_rejected(self):
        with self.assertRaises(DataError):
            quotation.calculate_quotation(
                self.catalogue, [{"sku": "IR-001", "qty": "2.5"}]
            )

    def test_empty_selection_rejected(self):
        with self.assertRaises(DataError) as ctx:
            quotation.calculate_quotation(self.catalogue, [], "0")
        self.assertIn("Не выбран", str(ctx.exception))

    def test_unknown_sku_rejected(self):
        with self.assertRaises(DataError):
            quotation.calculate_quotation(
                self.catalogue, [{"sku": "XX-999", "qty": "1"}]
            )

    def test_same_name_different_sku_separate(self):
        catalogue = quotation.load_catalogue(self.write_csv(
            "sku,name,category,price\n"
            "A-01,Чехол,Аксессуары,500\n"
            "A-02,Чехол,Аксессуары,700\n"
        ))
        calc = quotation.calculate_quotation(catalogue, [
            {"sku": "A-01", "qty": "1"},
            {"sku": "A-02", "qty": "1"},
        ], "0")
        self.assertEqual(len(calc["rows"]), 2)
        self.assertEqual(calc["subtotal"], Decimal("1200.00"))

    def test_duplicate_positions_merged(self):
        calc = quotation.calculate_quotation(self.catalogue, [
            {"sku": "IR-001", "qty": "2"},
            {"sku": "IR-001", "qty": "3"},
        ], "10")
        # 2 + 3 позиций — одна строка, количество 5:
        self.assertEqual(calc["rows"][0]["qty"], Decimal("5"))
        self.assertEqual(calc["subtotal"], Decimal("22950.00"))


class QuotationDetailsTests(CatalogueTestCase):
    """Обязательные/необязательные реквизиты предложения."""

    def _catalogue(self):
        return quotation.load_catalogue(self.write_valid_catalogue())

    def test_number_auto_generated(self):
        details = quotation.validate_details({})
        self.assertRegex(details["number"], r"^КП-\d{8}-\d{4}$")

    def test_number_explicit_preserved(self):
        details = quotation.validate_details({"number": "  КП-тест-001  "})
        self.assertEqual(details["number"], "КП-тест-001")

    def test_empty_details_stay_empty(self):
        details = quotation.validate_details({})
        self.assertEqual(details["supplier"], "")
        self.assertEqual(details["recipient"], "")
        self.assertEqual(details["valid_until"], "")
        self.assertEqual(details["comment"], "")

    def test_comment_length_limited(self):
        with self.assertRaises(DataError):
            quotation.validate_details({"comment": "К" * 301})


class QuotationPdfTests(CatalogueTestCase):
    """Генерация PDF и соответствие содержимого выбору."""

    def _render(self, context: dict) -> str:
        environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=jinja2.select_autoescape(["html"]),
        )
        return environment.get_template("quotation.html").render(**context)

    def test_pdf_created_unique_names(self):
        catalogue = quotation.load_catalogue(self.write_valid_catalogue())
        positions = [{"sku": "IR-001", "qty": "3"},
                     {"sku": "IR-002", "qty": "2"}]
        first = quotation.create_quotation_pdf(catalogue, positions, "10")
        second = quotation.create_quotation_pdf(catalogue, positions, "10")
        self.assertNotEqual(first, second)
        for path in (first, second):
            self.assertTrue(path.is_file(), path)
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"%PDF"), path)
            self.assertGreater(len(raw), 5000, path)
        self.assertIn("quotation_", first.name)

    def test_pdf_contains_selected_category_products_only(self):
        """КП только по «Утюги»: товары других категорий не попадают."""
        catalogue = quotation.load_catalogue(self.write_csv(VALID_CATALOGUE))
        irons = quotation.filter_items(catalogue, "Утюги")
        positions = [{"sku": item["sku"], "qty": "1"} for item in irons]
        context = quotation.build_context(catalogue, positions, "15")
        html = " ".join(self._render(context).split())
        # Подытог 4590 + 2190 = 6780; скидка 15 % = 1017; итог 5763.
        self.assertEqual(context["subtotal"], "6 780,00")
        self.assertEqual(context["discount_amount"], "1 017,00")
        self.assertEqual(context["grand_total"], "5 763,00")
        self.assertIn("Утюг паровой HomePro 2400", html)
        self.assertIn("Утюг компактный Travel", html)
        self.assertNotIn("Стиральная машина Aqua 7", html)
        self.assertIn("Скидка 15 %", html)
        self.assertIn("5 763,00", html)

    def test_discount_zero_absent_from_html(self):
        catalogue = quotation.load_catalogue(self.write_valid_catalogue())
        context = quotation.build_context(
            catalogue, [{"sku": "IR-001", "qty": "2"}], "0"
        )
        html = self._render(context)
        self.assertNotIn("Скидка", html)
        self.assertIn("Итого без скидки", html)
        self.assertEqual(context["grand_total"], "9 180,00")

    def test_empty_supplier_omitted_from_html(self):
        catalogue = quotation.load_catalogue(self.write_valid_catalogue())
        context = quotation.build_context(
            catalogue, [{"sku": "IR-001", "qty": "1"}], "0", {"supplier": ""}
        )
        html = " ".join(self._render(context).split())
        self.assertNotIn("Поставщик", html)
        # Номер сгенерирован автоматически:
        self.assertIn("№ КП-", html)

    def test_filled_details_in_html(self):
        catalogue = quotation.load_catalogue(self.write_valid_catalogue())
        context = quotation.build_context(
            catalogue, [{"sku": "IR-001", "qty": "1"}], "10",
            {"supplier": "ООО «Уютный дом» (демо)", "recipient": "ИП Петров П.П.",
             "valid_until": "14 дней", "comment": "Условные данные для демонстрации."}
        )
        html = " ".join(self._render(context).split())
        for value in ("ООО «Уютный дом» (демо)", "ИП Петров П.П.",
                      "14 дней", "Условные данные для демонстрации.",
                      "Скидка 10 %"):
            self.assertIn(value, html)


class PickDemoPositionsTests(CatalogueTestCase):
    """Выбор позиций для кнопки «Заполнить пример» из реального каталога."""

    def test_demo_catalogue_positions(self):
        catalogue = quotation.load_catalogue(self.write_csv(VALID_CATALOGUE))
        positions = quotation.pick_demo_positions(catalogue)
        self.assertEqual(positions, [
            {"sku": "IR-001", "qty": 2},
            {"sku": "IR-002", "qty": 1},
        ])
        # Позиции сразу валидны для расчетов:
        calc = quotation.calculate_quotation(catalogue, positions, "10")
        self.assertEqual(calc["subtotal"], Decimal("11370.00"))

    def test_foreign_catalogue_first_real_items(self):
        """В чужом каталоге демо-SKU нет — берутся первые реальные товары."""
        catalogue = quotation.load_catalogue(self.write_csv(
            "sku,name,category,price\n"
            "ZZ-01,Вещь 1,Прочее,100\n"
            "ZZ-02,Вещь 2,Прочее,200\n"
            "ZZ-03,Вещь 3,Прочее,300\n"
        ))
        positions = quotation.pick_demo_positions(catalogue)
        self.assertEqual(positions, [
            {"sku": "ZZ-01", "qty": 2},
            {"sku": "ZZ-02", "qty": 1},
        ])

    def test_single_item_catalogue(self):
        catalogue = quotation.load_catalogue(self.write_csv(
            "sku,name,category,price\nZZ-01,Только один,Прочее,50\n"
        ))
        positions = quotation.pick_demo_positions(catalogue)
        self.assertEqual(positions, [{"sku": "ZZ-01", "qty": 2}])

    def test_partially_matching_demo_skus(self):
        """Найден только IR-001 — второй несуществующий не придумывается."""
        catalogue = quotation.load_catalogue(self.write_csv(
            "sku,name,category,price\n"
            "IR-001,Утюг HomePro,Утюги,4590\n"
        ))
        positions = quotation.pick_demo_positions(catalogue)
        self.assertEqual(positions, [{"sku": "IR-001", "qty": 2}])


if __name__ == "__main__":
    unittest.main()
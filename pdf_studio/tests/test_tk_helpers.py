"""Тесты шорткатов буфера обмена (gui/tk_helpers.py) — без Tk, чистая логика."""

import sys
import unittest
from pathlib import Path

_STUDIO_DIR = Path(__file__).resolve().parents[1]
if str(_STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(_STUDIO_DIR))

from gui.tk_helpers import action_for_keycode  # noqa: E402


class ShortcutKeycodeTests(unittest.TestCase):
    """Маппинг кодов клавиш на действия для Ctrl+V/C/X/A."""

    def test_paste_v(self):
        self.assertEqual(action_for_keycode(86), "paste")

    def test_copy_c(self):
        self.assertEqual(action_for_keycode(67), "copy")

    def test_cut_x(self):
        self.assertEqual(action_for_keycode(88), "cut")

    def test_select_all_a(self):
        self.assertEqual(action_for_keycode(65), "select_all")

    def test_unmapped_keycode_is_none(self):
        self.assertIsNone(action_for_keycode(90))  # Z — не шорткат

    def test_non_numeric_keycode_is_none(self):
        """Keycode приходит числом; мусор не должен вызывать исключение."""
        self.assertIsNone(action_for_keycode("abc"))
        self.assertIsNone(action_for_keycode(None))


if __name__ == "__main__":
    unittest.main()
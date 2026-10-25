import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from password_manager import (
    add_entry,
    connect_db,
    create_account,
    delete_entry,
    generate_password,
    get_entry,
    list_entries,
)


class PasswordGeneratorTests(unittest.TestCase):

    def test_default_password_length(self):
        self.assertEqual(len(generate_password()), 20)

    def test_minimum_and_maximum_length(self):
        self.assertEqual(len(generate_password(12)), 12)
        self.assertEqual(len(generate_password(64)), 64)

    def test_rejects_invalid_length(self):
        for length in (5, 11, 65, 100):
            with self.subTest(length=length):
                with self.assertRaises(ValueError):
                    generate_password(length)

    def test_rejects_non_integer_length(self):
        for length in (12.5, "20", True):
            with self.subTest(length=length):
                with self.assertRaises(ValueError):
                    generate_password(length)

    def test_excludes_ambiguous_characters(self):
        for _ in range(100):
            password = generate_password(32, exclude_ambiguous=True)
            for character in "0OolI1":
                self.assertNotIn(character, password)

    def test_lowercase_only(self):
        password = generate_password(
            20,
            use_uppercase=False,
            use_digits=False,
            use_symbols=False,
        )
        self.assertTrue(password.islower())
        self.assertTrue(password.isalpha())

    def test_uppercase_only(self):
        password = generate_password(
            20,
            use_lowercase=False,
            use_digits=False,
            use_symbols=False,
        )
        self.assertTrue(password.isupper())
        self.assertTrue(password.isalpha())

    def test_digits_only(self):
        password = generate_password(
            20,
            use_lowercase=False,
            use_uppercase=False,
            use_symbols=False,
        )
        self.assertTrue(password.isdigit())

    def test_contains_each_enabled_group(self):
        password = generate_password(20)
        self.assertTrue(any(c in "abcdefghijklmnopqrstuvwxyz" for c in password))
        self.assertTrue(any(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in password))
        self.assertTrue(any(c in "0123456789" for c in password))
        self.assertTrue(any(c in "!@#$%^&*()-_=+[]{};:,.?" for c in password))

    def test_minimum_special_characters(self):
        symbols = "!@#$%^&*()-_=+[]{};:,.?"
        password = generate_password(20, min_special=5)
        count = sum(character in symbols for character in password)
        self.assertGreaterEqual(count, 5)

    def test_excludes_uncomfortable_symbols(self):
        password = generate_password(32, exclude_uncomfortable=True)
        for character in "[]{};:,.?^":
            self.assertNotIn(character, password)

    def test_rejects_no_selected_groups(self):
        with self.assertRaises(ValueError):
            generate_password(
                20,
                use_lowercase=False,
                use_uppercase=False,
                use_digits=False,
                use_symbols=False,
            )

    def test_special_characters_require_symbols_enabled(self):
        with self.assertRaises(ValueError):
            generate_password(20, use_symbols=False, min_special=3)

    def test_rejects_invalid_minimum_special_count(self):
        for count in (-1, 21, 2.5, True):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    generate_password(20, min_special=count)

    def test_combines_both_exclusion_options(self):
        password = generate_password(
            32,
            exclude_ambiguous=True,
            exclude_uncomfortable=True,
        )
        for character in "0OolI1[]{};:,.?^":
            self.assertNotIn(character, password)


class PasswordDatabaseTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_password.db"
        self.conn = connect_db(self.db_path)
        self.cipher = Fernet.generate_key()
        self.cipher = Fernet(self.cipher)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_add_and_get_entry(self):
        add_entry(
            self.conn,
            self.cipher,
            "ExampleSite",
            "test_user",
            "Strong-Test-Password-123!",
        )

        result = get_entry(self.conn, self.cipher, "ExampleSite")

        self.assertIsNotNone(result)
        self.assertEqual(
            result,
            ("ExampleSite", "test_user", "Strong-Test-Password-123!"),
        )

    def test_list_entries_does_not_expose_passwords(self):
        add_entry(
            self.conn,
            self.cipher,
            "ExampleSite",
            "test_user",
            "Strong-Test-Password-123!",
        )

        entries = list_entries(self.conn)

        self.assertEqual(entries, [("ExampleSite", "test_user")])
        self.assertNotIn("Strong-Test-Password-123!", str(entries))

    def test_duplicate_service_is_rejected(self):
        add_entry(self.conn, self.cipher, "ExampleSite", "user1", "password-one")

        with self.assertRaises(sqlite3.IntegrityError):
            add_entry(self.conn, self.cipher, "examplesite", "user2", "password-two")

    def test_delete_entry(self):
        add_entry(self.conn, self.cipher, "ExampleSite", "test_user", "password")

        self.assertTrue(delete_entry(self.conn, "ExampleSite"))
        self.assertIsNone(get_entry(self.conn, self.cipher, "ExampleSite"))
        self.assertFalse(delete_entry(self.conn, "MissingSite"))

    def test_empty_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            add_entry(self.conn, self.cipher, "", "test_user", "password")

        with self.assertRaises(ValueError):
            add_entry(self.conn, self.cipher, "ExampleSite", "", "password")

        with self.assertRaises(ValueError):
            add_entry(self.conn, self.cipher, "ExampleSite", "test_user", "")

    @patch(
        "builtins.input",
        side_effect=[
            "NewTestSite",
            "new_user",
            "1",
            "д",
        ],
    )
    def test_create_account_generates_and_saves_password(self, mock_input):
        with patch(
            "password_manager.generate_password",
            return_value="Generated-Test-Password-123!",
        ):
            create_account(self.conn, self.cipher)

        result = get_entry(self.conn, self.cipher, "NewTestSite")

        self.assertIsNotNone(result)
        self.assertEqual(result[1], "new_user")
        self.assertEqual(result[2], "Generated-Test-Password-123!")

    @patch(
        "builtins.input",
        side_effect=[
            "TemporarySite",
            "temporary_user",
            "1",
            "н",
        ],
    )
    def test_declining_save_does_not_create_entry(self, mock_input):
        with patch(
            "password_manager.generate_password",
            return_value="Temporary-Test-Password-123!",
        ):
            create_account(self.conn, self.cipher)

        self.assertIsNone(get_entry(self.conn, self.cipher, "TemporarySite"))


if __name__ == "__main__":
    unittest.main()

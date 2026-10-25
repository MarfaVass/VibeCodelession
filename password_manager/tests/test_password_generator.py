import unittest
from password_manager import generate_password

class PasswordGeneratorTests(unittest.TestCase):
    def test_length(self):
        self.assertEqual(len(generate_password(20)), 20)

    def test_excludes_ambiguous_characters(self):
        for _ in range(100):
            password = generate_password(32, exclude_ambiguous=True)
            for character in "0OolI1":
                self.assertNotIn(character, password)

    def test_invalid_length(self):
        with self.assertRaises(ValueError):
            generate_password(5)

if __name__ == "__main__":
    unittest.main()

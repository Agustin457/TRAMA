import unittest
import pandas as pd
from src.extract import clean_string_code, clean_price

class TestExtractCleaning(unittest.TestCase):
    def test_clean_string_code(self):
        self.assertEqual(clean_string_code(123.0), "123")
        self.assertEqual(clean_string_code("123.0"), "123")
        self.assertEqual(clean_string_code(" 456-A "), "456-A")
        self.assertEqual(clean_string_code(None), "")
        self.assertEqual(clean_string_code(""), "")

    def test_clean_price(self):
        self.assertEqual(clean_price(100.5), 100.5)
        self.assertEqual(clean_price("100.5"), 100.5)
        self.assertEqual(clean_price("$ 1.250,75"), 1250.75)
        self.assertEqual(clean_price(" 815722.0 "), 815722.0)
        self.assertEqual(clean_price(""), 0.0)
        self.assertEqual(clean_price(None), 0.0)

if __name__ == '__main__':
    unittest.main()

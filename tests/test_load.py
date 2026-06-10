import unittest
import tempfile
import os
import pandas as pd
from src.load import load_to_csv, load_to_excel

class TestLoad(unittest.TestCase):
    def test_load_to_csv_saves_file(self):
        df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            load_to_csv(df, path)
            self.assertTrue(os.path.exists(path))
            
            # Leer y comparar
            df_read = pd.read_csv(path)
            self.assertEqual(len(df_read), 2)
            self.assertEqual(df_read.iloc[0]["col2"], "a")

    def test_load_to_excel_saves_file(self):
        df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.xlsx")
            load_to_excel(df, path)
            self.assertTrue(os.path.exists(path))
            
            # Leer y comparar
            df_read = pd.read_excel(path)
            self.assertEqual(len(df_read), 2)
            self.assertEqual(df_read.iloc[1]["col2"], "b")

if __name__ == '__main__':
    unittest.main()

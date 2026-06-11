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

    def test_extract_hierarchical_rotring(self):
        from src.extract import extract_standardized_df
        import tempfile
        import os
        
        # Create a mock excel with Rotring structure
        data = {
            "CODIGO": [None]*16 + ["CODIGO", "91100", "91101", "91103", None, "200,91100", "200,91101"],
            "DESCRIPCION": [None]*16 + ["DESCRIPCION", "Acrilico Ordoñez x 50ml", "Blanco de titanio", "Amarillo medio", "PAPELES BLANCOS", "Acrilico Ordoñez x 200ml", "Blanco de titanio"],
            "UNITARIO EN PESOS": [None]*16 + ["UNITARIO EN PESOS", None, "46,90", "46,90", None, None, "144,50"]
        }
        df = pd.DataFrame(data)
        
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name
            df.to_excel(tmp_path, index=False, sheet_name="Hoja1")
            
        try:
            res_df = extract_standardized_df(tmp_path, "Hoja1", "ROTRING")
            self.assertEqual(len(res_df), 3)
            
            # Row 1: 91101 -> Acrilico Ordoñez x 50ml Blanco de titanio
            row1 = res_df[res_df['sku_proveedor'] == "91101"].iloc[0]
            self.assertEqual(row1['nombre_original'], "ACRILICO ORDOÑEZ X 50ML BLANCO DE TITANIO")
            self.assertEqual(row1['precio_crudo'], 46.90)
            
            # Row 2: 91103 -> Acrilico Ordoñez x 50ml Amarillo medio
            row2 = res_df[res_df['sku_proveedor'] == "91103"].iloc[0]
            self.assertEqual(row2['nombre_original'], "ACRILICO ORDOÑEZ X 50ML AMARILLO MEDIO")
            
            # Row 3: 200,91101 -> Acrilico Ordoñez x 200ml Blanco de titanio (cleared the category reset correctly)
            row3 = res_df[res_df['sku_proveedor'] == "200,91101"].iloc[0]
            self.assertEqual(row3['nombre_original'], "ACRILICO ORDOÑEZ X 200ML BLANCO DE TITANIO")
            
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == '__main__':
    unittest.main()

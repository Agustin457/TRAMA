import unittest
import tempfile
import os
import pandas as pd
from sqlalchemy.orm import Session
from src.models import init_db, get_db_session, ProductoProveedor, HistorialPrecio, Proveedor
from src.import_providers import calculate_cost_cascade, import_supplier_data

class TestImportProviders(unittest.TestCase):
    def test_calculate_cost_cascade_general(self):
        config = {
            "taxes": {
                "iva": 0.21,
                "iibb": 0.035,
                "cheque": 0.012,
                "sellos": 0.01
            }
        }
        
        # Test para ALE (IVA ya incluido)
        # Costo neto = 121 / 1.21 = 100
        # Costo unificado = 100 * 1.21 * 1.035 * 1.012 * 1.01 = 128.01
        cost_ale = calculate_cost_cascade(121.00, "ALE", config)
        self.assertEqual(cost_ale, 128.01)

        # Test para POWERLAND (IVA no incluido)
        # Costo neto = 100
        # Costo unificado = 100 * 1.21 * 1.035 * 1.012 * 1.01 = 128.01
        cost_pl = calculate_cost_cascade(100.00, "POWERLAND", config)
        self.assertEqual(cost_pl, 128.01)

if __name__ == '__main__':
    unittest.main()

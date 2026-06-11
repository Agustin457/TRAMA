import unittest
import tempfile
import os
import pandas as pd
from sqlalchemy.orm import Session
from src.models import init_db, get_db_session, ProductoProveedor, HistorialPrecio, Proveedor
from src.import_providers import calculate_cost_with_iva, import_supplier_data

class TestImportProviders(unittest.TestCase):
    def test_calculate_cost_with_iva(self):
        # Test para ALE/Powerland (IVA ya incluido)
        cost_ale = calculate_cost_with_iva(100.00, True)
        self.assertEqual(cost_ale, 100.00)

        # Test para Plantec (IVA no incluido)
        # Costo con IVA = 100 * 1.21 = 121.00
        cost_pl = calculate_cost_with_iva(100.00, False)
        self.assertEqual(cost_pl, 121.00)

if __name__ == '__main__':
    unittest.main()

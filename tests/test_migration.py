import unittest
import tempfile
import os
import pandas as pd
from sqlalchemy.orm import Session
from src.models import init_db, get_db_session, CatalogoMaestro
from src.migrate_woocommerce import migrate_woocommerce_csv

class TestMigration(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        init_db(self.temp_db_path)
        self.SessionFactory = get_db_session(self.temp_db_path)
        
        # Crear CSV de prueba de WooCommerce
        self.temp_csv = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        self.temp_csv_path = self.temp_csv.name
        self.temp_csv.close()

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)
        if os.path.exists(self.temp_csv_path):
            os.remove(self.temp_csv_path)

    def test_migrate_woocommerce_csv(self):
        # Crear datos de prueba para WooCommerce CSV
        mock_data = [
            {"ID": 999, "SKU": "TEST-SKU", "Name": "Lapicera Bic Fina Azul", "Regular price": 140.0, "Meta: _wcb_barcode": "1234567890123"}
        ]
        pd.DataFrame(mock_data).to_csv(self.temp_csv_path, index=False)
        
        # Ejecutar migración
        count = migrate_woocommerce_csv(self.temp_csv_path, self.temp_db_path)
        self.assertEqual(count, 1)
        
        # Verificar en base de datos
        session: Session = self.SessionFactory()
        try:
            prod = session.query(CatalogoMaestro).filter(CatalogoMaestro.master_sku == "TEST-SKU").first()
            self.assertIsNotNone(prod)
            self.assertEqual(prod.nombre_normalizado, "LAPICERA BIC FINA AZUL")
            self.assertEqual(prod.codigo_barras, "1234567890123")
            self.assertEqual(prod.precio_venta, 0.0)
            self.assertEqual(prod.precio_costo, 0.0)
            self.assertEqual(prod.marca, "BIC")
        finally:
            session.close()

if __name__ == '__main__':
    unittest.main()

import unittest
import tempfile
import os
from sqlalchemy.orm import Session
from src.models import init_db, get_db_session, CatalogoMaestro, ProductoProveedor, Proveedor

class TestDatabaseOperations(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        init_db(self.temp_db_path)
        self.SessionFactory = get_db_session(self.temp_db_path)

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_crud_operations(self):
        session: Session = self.SessionFactory()
        try:
            # 1. Create Proveedor y Producto Maestro
            new_prov = Proveedor(id="TEST", nombre="Proveedor Test")
            session.add(new_prov)
            
            new_prod = CatalogoMaestro(
                master_sku="ESC-BIC-CRI-AZU",
                codigo_barras="7790000111222",
                nombre_normalizado="LAPICERA BIC CRISTAL AZUL",
                marca="BIC",
                categoria="ESCRITURA",
                precio_costo=100.0,
                margen_ganancia=0.40,
                precio_venta=140.0
            )
            session.add(new_prod)
            session.commit()

            # 2. Read
            prod_db = session.query(CatalogoMaestro).filter(CatalogoMaestro.master_sku == "ESC-BIC-CRI-AZU").first()
            self.assertIsNotNone(prod_db)
            self.assertEqual(prod_db.nombre_normalizado, "LAPICERA BIC CRISTAL AZUL")
            self.assertEqual(prod_db.precio_venta, 140.0)

            # 3. Create ProductoProveedor vinculado
            prov_prod = ProductoProveedor(
                proveedor_id="TEST",
                sku_proveedor="BIC123",
                nombre_original="BOLIGRAFO BIC AZUL CRISTAL",
                precio_crudo=80.0,
                costo_calculado=100.0,
                stock_crudo=10,
                master_sku="ESC-BIC-CRI-AZU",
                estado_unificacion="APROBADO"
            )
            session.add(prov_prod)
            session.commit()
            
            # Verificar relación
            self.assertEqual(len(prod_db.productos_proveedor), 1)
            self.assertEqual(prod_db.productos_proveedor[0].sku_proveedor, "BIC123")

        finally:
            session.close()

if __name__ == '__main__':
    unittest.main()

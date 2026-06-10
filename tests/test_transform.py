import unittest
import tempfile
import os
from sqlalchemy.orm import Session
from src.models import init_db, get_db_session, CatalogoMaestro, ProductoProveedor, Proveedor
from src.transform import consolidate_master_catalog

class TestTransformConsolidation(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        init_db(self.temp_db_path)
        self.SessionFactory = get_db_session(self.temp_db_path)

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_consolidate_master_catalog_updates_costs_and_stock(self):
        session: Session = self.SessionFactory()
        try:
            # Los proveedores 'ALE' y 'POWERLAND' son precargados automáticamente por init_db.
            # Verificamos que existen:
            p1 = session.query(Proveedor).filter(Proveedor.id == "ALE").first()
            p2 = session.query(Proveedor).filter(Proveedor.id == "POWERLAND").first()
            self.assertIsNotNone(p1)
            self.assertIsNotNone(p2)
            
            # Setup Master Product
            m_prod = CatalogoMaestro(
                master_sku="ESC-BIC-CRI-AZU",
                nombre_normalizado="LAPICERA BIC CRISTAL AZUL",
                marca="BIC",
                categoria="ESCRITURA",
                precio_costo=0.0,
                margen_ganancia=0.40,
                precio_venta=0.0
            )
            session.add(m_prod)
            session.commit()

            # Vincular 2 productos de proveedor con costos y stock diferentes
            pp1 = ProductoProveedor(
                proveedor_id="ALE",
                sku_proveedor="1001",
                nombre_original="Boligrafo Bic Cristal Azul",
                precio_crudo=80.0,
                costo_calculado=100.0,
                stock_crudo=15,
                master_sku="ESC-BIC-CRI-AZU",
                estado_unificacion="APROBADO"
            )
            pp2 = ProductoProveedor(
                proveedor_id="POWERLAND",
                sku_proveedor="PL-99",
                nombre_original="Lapicera Bic Azul",
                precio_crudo=90.0,
                costo_calculado=120.0,
                stock_crudo=25,
                master_sku="ESC-BIC-CRI-AZU",
                estado_unificacion="APROBADO"
            )
            session.add_all([pp1, pp2])
            session.commit()
            
            # Ejecutar consolidación
            df = consolidate_master_catalog(self.temp_db_path)
            
            # Verificar en base de datos
            m_prod_updated = session.query(CatalogoMaestro).filter(CatalogoMaestro.master_sku == "ESC-BIC-CRI-AZU").first()
            
            # Costo debe ser el máximo (120.0)
            self.assertEqual(m_prod_updated.precio_costo, 120.0)
            
            # Venta debe ser 120.0 * 1.40 = 168.0
            self.assertEqual(m_prod_updated.precio_venta, 168.0)
            
            # En el DataFrame de retorno, el stock unificado debe ser 15 + 25 = 40
            row = df[df["SKU_Maestro"] == "ESC-BIC-CRI-AZU"].iloc[0]
            self.assertEqual(row["Stock_Total_Consolidado"], 40)
            self.assertEqual(row["Precio_Costo_Consolidado"], 120.0)
            self.assertEqual(row["Precio_Venta_PVP"], 168.0)

        finally:
            session.close()

if __name__ == '__main__':
    unittest.main()

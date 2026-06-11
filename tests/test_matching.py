import unittest
import tempfile
import os
from sqlalchemy.orm import Session
from src.models import init_db, get_db_session, CatalogoMaestro, ProductoProveedor, CoincidenciaPendiente, Proveedor
from src.matching import clean_and_normalize_name, extract_brand, run_matching_engine, approve_pending_match, reject_pending_match

class TestMatchingEngine(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        init_db(self.temp_db_path)
        self.SessionFactory = get_db_session(self.temp_db_path)

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_clean_and_normalize_name(self):
        self.assertEqual(clean_and_normalize_name("Lapicera Bic Azul"), "LAPICERA BIC AZUL")
        self.assertEqual(clean_and_normalize_name("Lap. Bic Azul"), "LAPICERA BIC AZUL")
        self.assertEqual(clean_and_normalize_name("Bic Cristal Ázúl"), "BIC CRISTAL AZUL")
        self.assertEqual(clean_and_normalize_name("Pint. Acrilica Roja"), "PINTURA ACRILICA ROJA")

    def test_extract_brand(self):
        self.assertEqual(extract_brand("Lapicera Bic Cristal Azul"), "BIC")
        self.assertEqual(extract_brand("Estilografo Rotring Isograph"), "ROTRING")
        self.assertEqual(extract_brand("Cuaderno de dibujo"), "VARIOS")  # Both are blacklisted, returns VARIOS
        self.assertEqual(extract_brand("Acme de dibujo"), "ACME")  # Acme is not blacklisted, returns ACME

    def test_matching_flow(self):
        session: Session = self.SessionFactory()
        try:
            # Los proveedores son precargados automáticamente por init_db.
            p1 = session.query(Proveedor).filter(Proveedor.id == "ALE").first()
            self.assertIsNotNone(p1)
            
            # Setup Catalog
            m_prod = CatalogoMaestro(
                master_sku="ESC-BIC-CRI-AZU",
                codigo_barras="7798071680551",
                nombre_normalizado="LAPICERA BIC CRISTAL AZUL",
                marca="BIC",
                categoria="ESCRITURA",
                precio_costo=100.0,
                margen_ganancia=0.40,
                precio_venta=140.0
            )
            session.add(m_prod)
            session.commit()

            # 1. Producto del proveedor con EAN idéntico (debe auto-asociarse)
            pp_ean = ProductoProveedor(
                proveedor_id="ALE",
                sku_proveedor="ALE-EAN-1",
                nombre_original="Bic Cristal Azul",
                precio_crudo=80.0,
                costo_calculado=100.0,
                codigo_barras="7798071680551",
                estado_unificacion="PENDIENTE"
            )
            
            # 2. Producto del proveedor con nombre muy similar sin EAN (debe generar coincidencia pendiente)
            pp_fuzzy = ProductoProveedor(
                proveedor_id="POWERLAND",
                sku_proveedor="ALE-FUZ-1",
                nombre_original="Lapicera Bic Azul",
                precio_crudo=80.0,
                costo_calculado=100.0,
                codigo_barras=None,
                estado_unificacion="PENDIENTE"
            )
            session.add_all([pp_ean, pp_fuzzy])
            session.commit()

            # Ejecutar motor de matching
            results = run_matching_engine(self.temp_db_path)
            
            self.assertEqual(results["ean_automatch"], 1)
            self.assertEqual(results["pending_manual_review"], 1)
            
            # Verificar que pp_ean se auto-unificó
            pp_ean_db = session.query(ProductoProveedor).filter(ProductoProveedor.sku_proveedor == "ALE-EAN-1").first()
            self.assertEqual(pp_ean_db.master_sku, "ESC-BIC-CRI-AZU")
            self.assertEqual(pp_ean_db.estado_unificacion, "APROBADO")
            
            # Verificar coincidencia pendiente para pp_fuzzy
            pending = session.query(CoincidenciaPendiente).filter(CoincidenciaPendiente.producto_proveedor_id == pp_fuzzy.id).first()
            self.assertIsNotNone(pending)
            self.assertEqual(pending.master_sku_sugerido, "ESC-BIC-CRI-AZU")
            self.assertEqual(pending.estado, "PENDIENTE")
            
            # Aprobar la coincidencia pendiente manualmente
            success = approve_pending_match(pending.id, db_path=self.temp_db_path)
            self.assertTrue(success)
            
            # Verificar estado posterior
            session.expire_all()
            pp_fuzzy_db = session.query(ProductoProveedor).filter(ProductoProveedor.sku_proveedor == "ALE-FUZ-1").first()
            self.assertEqual(pp_fuzzy_db.master_sku, "ESC-BIC-CRI-AZU")
            self.assertEqual(pp_fuzzy_db.estado_unificacion, "APROBADO")

        finally:
            session.close()

    def test_abbreviation_expansion_and_cleanup(self):
        from src.matching import expand_abbreviations_in_name, clean_existing_abbreviations
        # Test expand_abbreviations_in_name
        self.assertEqual(expand_abbreviations_in_name("MARC. ROTRING NEGRO"), "MARCADOR ROTRING NEGRO")
        self.assertEqual(expand_abbreviations_in_name("BOLIG. BIC AZUL"), "BOLIGRAFO BIC AZUL")
        self.assertEqual(expand_abbreviations_in_name("LAP. ROJA"), "LAPICERA ROJA")
        self.assertEqual(expand_abbreviations_in_name("MARC.CERA COLOR ALBORADA *12"), "MARCADOR CERA COLOR ALBORADA *12")
        self.assertEqual(expand_abbreviations_in_name("BOLIG.0.5MM AZUL"), "BOLIGRAFO 0.5MM AZUL")
        self.assertEqual(expand_abbreviations_in_name("ROLLER FILGO 1.0MM NEGRO"), "ROLLER FILGO 1.0MM NEGRO")
        
        session: Session = self.SessionFactory()
        try:
            # Insert abbreviated product in catalog
            m_prod = CatalogoMaestro(
                master_sku="ESC-ROTR-MAR-NEGR",
                codigo_barras="11223344",
                nombre_normalizado="MARC. ROTRING NEGRO",
                marca="ROTRING",
                categoria="ESCRITURA",
                precio_costo=100.0,
                margen_ganancia=0.40,
                precio_venta=140.0
            )
            session.add(m_prod)
            session.commit()
            
            # Run cleanup
            updated_count = clean_existing_abbreviations(self.temp_db_path)
            self.assertEqual(updated_count, 1)
            
            # Verify clean name in DB
            session.expire_all()
            p_db = session.query(CatalogoMaestro).filter(CatalogoMaestro.master_sku == "ESC-ROTR-MAR-NEGR").first()
            self.assertEqual(p_db.nombre_normalizado, "MARCADOR ROTRING NEGRO")
        finally:
            session.close()

if __name__ == '__main__':
    unittest.main()

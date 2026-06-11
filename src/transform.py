import pandas as pd
from sqlalchemy.orm import Session
from src.utils.logger import setup_logger
from src.models import get_db_session, CatalogoMaestro, ProductoProveedor

logger = setup_logger()

def consolidate_master_catalog(db_path: str = None) -> pd.DataFrame:
    """
    Recalcula los costos y stocks unificados de la tabla catalogo_maestro 
    basándose en los productos de proveedores vinculados (productos_proveedor).
    Luego exporta y retorna un DataFrame con los productos listos para WooCommerce.
    """
    logger.info("Recalculando consolidación de catálogo maestro (Costos y Stock)...")
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    
    try:
        # Obtener todos los productos del catálogo maestro
        master_products = session.query(CatalogoMaestro).all()
        
        for m_prod in master_products:
            # Buscar todos los productos de proveedores vinculados activos a este SKU
            linked_prov_products = session.query(ProductoProveedor).filter(
                ProductoProveedor.master_sku == m_prod.master_sku,
                ProductoProveedor.estado_unificacion == 'APROBADO'
            ).all()
            
            if linked_prov_products:
                # 1. Regla de Costo: Tomar el costo máximo para proteger márgenes financieros
                max_cost_prov = max(linked_prov_products, key=lambda p: p.costo_calculado)
                max_cost = max_cost_prov.costo_calculado
                m_prod.precio_costo = max_cost
                
                # 2. Regla de Stock: Sumatoria del stock físico de todos los proveedores mapeados
                total_stock = sum(p.stock_crudo for p in linked_prov_products)
                
                # 3. Recalcular precio de venta
                m_prod.precio_venta = round(max_cost * (1 + m_prod.margen_ganancia), 2)
            else:
                total_stock = 0
                
        session.commit()
        
        # 4. Generar DataFrame consolidado
        data = []
        for m_prod in master_products:
            # Obtener stock recalculado
            linked_prov_products = session.query(ProductoProveedor).filter(
                ProductoProveedor.master_sku == m_prod.master_sku,
                ProductoProveedor.estado_unificacion == 'APROBADO'
            ).all()
            total_stock = sum(p.stock_crudo for p in linked_prov_products) if linked_prov_products else 0
            
            if linked_prov_products:
                max_cost_prov = max(linked_prov_products, key=lambda p: p.costo_calculado)
                costo_lista = max_cost_prov.precio_crudo
                incluye_iva = "SI" if max_cost_prov.proveedor_id in ("ALE", "POWERLAND") else "NO"
            else:
                costo_lista = m_prod.precio_costo
                incluye_iva = "SI"
                
            data.append({
                "SKU_Maestro": m_prod.master_sku,
                "Nombre_Normalizado": m_prod.nombre_normalizado,
                "Marca": m_prod.marca,
                "Categoria": m_prod.categoria,
                "Costo_Lista": costo_lista,
                "Incluye_IVA": incluye_iva,
                "Costo_con_IVA": m_prod.precio_costo,
                "Margen_Ganancia": m_prod.margen_ganancia,
                "PVP_Sugerido": m_prod.precio_venta,
                "Stock_Total_Consolidado": total_stock,
                "Codigo_Barras": m_prod.codigo_barras or "",
                "ID_WooCommerce": m_prod.id_woocommerce or ""
            })
            
        df = pd.DataFrame(data)
        logger.info(f"Consolidación exitosa. Catálogo maestro cuenta con {len(df)} registros.")
        return df
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error durante la consolidación del catálogo maestro: {e}", exc_info=True)
        raise
    finally:
        session.close()

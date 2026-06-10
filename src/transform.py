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
                max_cost = max(p.costo_calculado for p in linked_prov_products)
                m_prod.precio_costo = max_cost
                
                # 2. Regla de Stock: Sumatoria del stock físico de todos los proveedores mapeados
                total_stock = sum(p.stock_crudo for p in linked_prov_products)
                
                # 3. Recalcular precio de venta
                m_prod.precio_venta = round(max_cost * (1 + m_prod.margen_ganancia), 2)
            else:
                # Si no tiene proveedores vinculados activos (por ejemplo, producto exclusivo WooCommerce),
                # se mantiene su stock actual de WooCommerce (se asume 0 si no se cargó)
                total_stock = 0
                
            # Nota: Podríamos almacenar la cantidad unificada en una columna si lo deseamos.
            # Para exportar, simplemente calculamos el stock disponible.
            
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
            
            data.append({
                "SKU_Maestro": m_prod.master_sku,
                "Nombre_Normalizado": m_prod.nombre_normalizado,
                "Marca": m_prod.marca,
                "Categoria": m_prod.categoria,
                "Precio_Costo_Consolidado": m_prod.precio_costo,
                "Margen_Ganancia": m_prod.margen_ganancia,
                "Precio_Venta_PVP": m_prod.precio_venta,
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

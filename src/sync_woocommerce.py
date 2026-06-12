#!/usr/bin/env python3
import os
import sys
import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

# Set python path and working directory
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_dir)
if project_dir not in sys.path:
    sys.path.append(project_dir)

from src.utils.logger import setup_logger
from src.utils.helpers import load_config
from src.models import get_db_session, CatalogoMaestro, ProductoProveedor

logger = setup_logger()

def sync():
    config = load_config("config.yaml")
    wc_config = config.get("woocommerce", {})
    
    url = wc_config.get("url", "https://tramabuenosaires.com.ar").rstrip("/")
    consumer_key = wc_config.get("consumer_key", "ck_...")
    consumer_secret = wc_config.get("consumer_secret", "cs_...")
    dry_run = wc_config.get("dry_run", True)
    
    db_path = config.get("paths", {}).get("db_path")
    
    logger.info("Iniciando proceso de sincronización con WooCommerce...")
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    
    try:
        # 1. Obtener todos los productos mapeados a WooCommerce
        products = session.query(CatalogoMaestro).filter(CatalogoMaestro.id_woocommerce != None).all()
        logger.info(f"Productos mapeados en la base de datos para sincronizar: {len(products)}")
        
        if not products:
            logger.info("No hay productos vinculados con ID_WooCommerce para actualizar.")
            return
            
        updates = []
        for p in products:
            # Calcular el stock consolidado actual (sumatoria de proveedores aprobados)
            total_stock = session.query(func.sum(ProductoProveedor.stock_crudo)).filter(
                ProductoProveedor.master_sku == p.master_sku,
                ProductoProveedor.estado_unificacion == 'APROBADO'
            ).scalar() or 0
            
            updates.append({
                "id": p.id_woocommerce,
                "regular_price": str(round(p.precio_venta, 2)),
                "manage_stock": True,
                "stock_quantity": int(total_stock)
            })
            
        # 2. Sincronizar en lotes de 100 productos (límite de la API de WooCommerce)
        batch_size = 100
        logger.info(f"Sincronizando en lotes de {batch_size} a {url}...")
        
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i+batch_size]
            logger.info(f"Procesando lote {i // batch_size + 1} ({len(batch)} productos)...")
            
            if dry_run:
                logger.info(f"[SIMULACIÓN] Lote {i // batch_size + 1} - Cambios que se aplicarían:")
                for item in batch:
                    logger.info(f"  -> ID WooCommerce: {item['id']} | Nuevo PVP: ${item['regular_price']} | Nuevo Stock: {item['stock_quantity']}")
            else:
                endpoint = f"{url}/wp-json/wc/v3/products/batch"
                try:
                    response = requests.post(
                        endpoint,
                        json={"update": batch},
                        auth=(consumer_key, consumer_secret),
                        timeout=30
                    )
                    if response.status_code == 200:
                        logger.info(f"-> Lote {i // batch_size + 1} sincronizado exitosamente en la web.")
                    else:
                        logger.error(f"-> Error al sincronizar lote {i // batch_size + 1}: Código {response.status_code} - {response.text}")
                except Exception as e:
                    logger.error(f"-> Error de red en lote {i // batch_size + 1}: {e}")
                    
        logger.info("Sincronización con WooCommerce finalizada.")
        
    finally:
        session.close()

if __name__ == "__main__":
    sync()

import os
import glob
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import Session
from src.utils.logger import setup_logger
from src.utils.helpers import load_config
from src.models import init_db, get_db_session, ProductoProveedor, HistorialPrecio, Proveedor
from src.extract import extract_standardized_df

logger = setup_logger()

def calculate_cost_with_iva(raw_price: float, has_iva: bool, iva_rate: float = 0.21) -> float:
    """
    Calcula el costo base con IVA incluido.
    Si el proveedor no tiene IVA incluido (has_iva = False), se lo agrega multiplicando por (1 + iva_rate).
    """
    if pd.isna(raw_price) or raw_price <= 0:
        return 0.0
        
    if has_iva:
        # Ya tiene IVA incluido (ALE, Powerland)
        costo_calculado = raw_price
    else:
        # No tiene IVA incluido, se le suma (Plantec)
        costo_calculado = raw_price * (1 + iva_rate)
        
    return round(costo_calculado, 2)

def import_supplier_data(provider_id: str, db_path: str = None, config_path: str = "config.yaml") -> int:
    """
    Extrae, calcula impuestos e importa datos para un proveedor.
    Soporta múltiples archivos físicos mediante coincidencia de patrones (wildcards).
    Registra variaciones de costos en la tabla 'historial_precios'.
    """
    logger.info(f"Iniciando importación para proveedor: '{provider_id}'")
    
    config = load_config(config_path)
    raw_dir = config.get("paths", {}).get("raw_data_dir", "data/raw")
    processed_dir = config.get("paths", {}).get("processed_data_dir", "data/processed")
    providers_cfg = config.get("extraction", {}).get("providers", {})
    
    p_id_lower = provider_id.lower()
    if p_id_lower not in providers_cfg:
        raise ValueError(f"Proveedor '{provider_id}' no está configurado en config.yaml.")
        
    p_cfg = providers_cfg[p_id_lower]
    has_iva = p_cfg.get("has_iva", False)
    
    # Preferir archivos preprocesados (normalizados) si existen en data/processed/
    # Si no existen, caer de vuelta a los archivos raw originales
    processed_fname = p_cfg.get("processed_filename")
    processed_files = sorted(glob.glob(os.path.join(processed_dir, processed_fname))) if processed_fname else []
    
    if processed_files:
        matching_files = processed_files
        sheet_to_use = "Sheet1"  # pandas usa Sheet1 por defecto al exportar con to_excel()
        logger.info(f"Usando {len(matching_files)} archivo(s) PREPROCESADO(S) para {provider_id.upper()}")
    else:
        raw_pattern = os.path.join(raw_dir, p_cfg["filename"])
        matching_files = glob.glob(raw_pattern)
        sheet_to_use = p_cfg["sheet"]
        logger.info(f"Sin archivos preprocesados, usando RAW para {provider_id.upper()}")
    
    if not matching_files:
        raise FileNotFoundError(
            f"No se encontraron archivos para proveedor {provider_id.upper()}. "
            f"Procesados buscados en: {processed_dir}/{processed_fname or '(sin configurar)'}"
        )
    
    logger.info(f"Archivos a importar para {provider_id}: {matching_files}")
    
    # Inicializar DB y Sesión
    init_db(db_path)
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    
    total_imported_count = 0
    price_change_count = 0
    warnings_count = 0
    
    try:
        # Verificar que el proveedor existe
        prov_obj = session.query(Proveedor).filter(Proveedor.id == provider_id.upper()).first()
        if not prov_obj:
            prov_obj = Proveedor(id=provider_id.upper(), nombre=f"Proveedor {provider_id.upper()}", margen_defecto=0.60)
            session.add(prov_obj)
            session.commit()

        # Obtener productos existentes de este proveedor para actualizar o auditar
        existing_products = {p.sku_proveedor: p for p in session.query(ProductoProveedor).filter(ProductoProveedor.proveedor_id == provider_id.upper()).all()}
        
        # Procesar cada archivo en bucle
        for file_path in matching_files:
            logger.info(f"Procesando archivo individual: {file_path}")
            archivo_nombre = os.path.basename(file_path)
            df = extract_standardized_df(file_path, sheet_name=sheet_to_use, provider_id=provider_id.upper())
            
            for _, row in df.iterrows():
                sku = row['sku_proveedor']
                nombre = row['nombre_original']
                precio_crudo = row['precio_crudo']
                barcode = row['codigo_barras']
                if pd.isna(barcode) or barcode == "":
                    barcode = None
                    
                # Calcular costo con IVA
                costo_calculado = calculate_cost_with_iva(precio_crudo, has_iva)
                
                if sku in existing_products:
                    # Actualizar existente
                    p_prov = existing_products[sku]
                    
                    # Auditar si cambia el precio
                    if p_prov.precio_crudo != precio_crudo:
                        price_change_count += 1
                        
                        # Alerta si el costo varía más del 50%
                        if p_prov.precio_crudo > 0:
                            pct_change = abs(precio_crudo - p_prov.precio_crudo) / p_prov.precio_crudo
                            if pct_change > 0.50:
                                logger.warning(f"[ALERTA PRECIO] El precio de {sku} ({nombre}) cambió un {pct_change*100:.1f}% de {p_prov.precio_crudo} a {precio_crudo}")
                                warnings_count += 1
                                
                        # Crear registro de historial
                        hist = HistorialPrecio(
                            producto_proveedor_id=p_prov.id,
                            precio_crudo_anterior=p_prov.precio_crudo,
                            precio_crudo_nuevo=precio_crudo,
                            costo_calculado_anterior=p_prov.costo_calculado,
                            costo_calculado_nuevo=costo_calculado
                        )
                        session.add(hist)
                    
                    p_prov.nombre_original = nombre
                    p_prov.precio_crudo = precio_crudo
                    p_prov.costo_calculado = costo_calculado
                    if barcode:
                        p_prov.codigo_barras = barcode
                    p_prov.archivo_origen = archivo_nombre
                    p_prov.last_imported_at = datetime.utcnow()
                    total_imported_count += 1
                else:
                    # Insertar nuevo
                    new_prov_prod = ProductoProveedor(
                        proveedor_id=provider_id.upper(),
                        sku_proveedor=sku,
                        nombre_original=nombre,
                        precio_crudo=precio_crudo,
                        costo_calculado=costo_calculado,
                        stock_crudo=10,  # Stock físico por defecto
                        codigo_barras=barcode,
                        estado_unificacion='PENDIENTE',
                        archivo_origen=archivo_nombre
                    )
                    session.add(new_prov_prod)
                    session.flush() # flush para obtener id del objeto insertado
                    
                    # Registrar en el mapa local para evitar colisiones si se repite en el mismo import
                    existing_products[sku] = new_prov_prod
                    total_imported_count += 1
                    
        session.commit()
        logger.info(f"Importación de '{provider_id.upper()}' finalizada: {total_imported_count} filas procesadas de {len(matching_files)} archivos. Cambios de precio: {price_change_count}. Alertas: {warnings_count}.")
        return total_imported_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error importando proveedor '{provider_id}': {e}", exc_info=True)
        raise
    finally:
        session.close()

if __name__ == "__main__":
    # Ingesta completa
    config = load_config("config.yaml")
    db_path = config.get("paths", {}).get("db_path", "data/etl_database.db")
    providers = config.get("extraction", {}).get("providers", {})
    
    for prov_name in providers.keys():
        import_supplier_data(prov_name, db_path=db_path)

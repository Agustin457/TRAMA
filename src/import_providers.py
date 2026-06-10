import os
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import Session
from src.utils.logger import setup_logger
from src.utils.helpers import load_config
from src.models import init_db, get_db_session, ProductoProveedor, HistorialPrecio, Proveedor
from src.extract import extract_ale, extract_powerland, extract_rotring

logger = setup_logger()

def calculate_cost_cascade(raw_price: float, provider_id: str, config: dict) -> float:
    """
    Calcula el costo neto neto aplicando la cascada impositiva de Argentina.
    """
    tax_cfg = config.get("taxes", {})
    iva_rate = tax_cfg.get("iva", 0.21)
    iibb_rate = tax_cfg.get("iibb", 0.035)
    cheque_rate = tax_cfg.get("cheque", 0.012)
    sellos_rate = tax_cfg.get("sellos", 0.01)
    
    # 1. Determinar costo neto (sin IVA)
    if provider_id.upper() == "ALE":
        # ALE ya incluye el IVA en sus precios crudos
        costo_neto = raw_price / (1 + iva_rate)
    else:
        # Powerland y Rotring no incluyen IVA en sus listas de precios
        costo_neto = raw_price
        
    # 2. Aplicar la cascada de impuestos
    # Costo final = costo_neto + IVA + Percepcion IIBB + Impuesto al cheque + Sellos
    costo_calculado = costo_neto * (1 + iva_rate) * (1 + iibb_rate) * (1 + cheque_rate) * (1 + sellos_rate)
    return round(costo_calculado, 2)

def import_supplier_data(provider_id: str, db_path: str = None, config_path: str = "config.yaml") -> int:
    """
    Extrae, calcula impuestos e inserta los datos de un proveedor en la tabla 'productos_proveedor'.
    Registra cambios de precios en la tabla 'historial_precios'.
    """
    logger.info(f"Iniciando importación para proveedor: '{provider_id}'")
    
    config = load_config(config_path)
    raw_dir = config.get("paths", {}).get("raw_data_dir", "data/raw")
    providers_cfg = config.get("extraction", {}).get("providers", {})
    
    p_id_lower = provider_id.lower()
    if p_id_lower not in providers_cfg:
        raise ValueError(f"Proveedor '{provider_id}' no está configurado en config.yaml.")
        
    p_cfg = providers_cfg[p_id_lower]
    file_path = os.path.join(raw_dir, p_cfg["filename"])
    sheet_name = p_cfg["sheet"]
    header_row = p_cfg["header_row"]
    
    # 1. Extraer datos usando pandas
    if p_id_lower == "ale":
        df = extract_ale(file_path, sheet_name=sheet_name, header_row=header_row)
    elif p_id_lower == "powerland":
        df = extract_powerland(file_path, sheet_name=sheet_name, header_row=header_row)
    elif p_id_lower == "rotring":
        df = extract_rotring(file_path, sheet_name=sheet_name, header_row=header_row)
    else:
        raise ValueError(f"Extractor no implementado para proveedor '{provider_id}'.")
        
    # 2. Inicializar base de datos y sesión
    init_db(db_path)
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    
    imported_count = 0
    price_change_count = 0
    warnings_count = 0
    
    try:
        # Verificar que el proveedor existe en la DB
        prov_obj = session.query(Proveedor).filter(Proveedor.id == provider_id.upper()).first()
        if not prov_obj:
            prov_obj = Proveedor(id=provider_id.upper(), nombre=f"Proveedor {provider_id.upper()}", margen_defecto=0.40)
            session.add(prov_obj)
            session.commit()

        # Obtener productos existentes de este proveedor para actualizar o auditar
        existing_products = {p.sku_proveedor: p for p in session.query(ProductoProveedor).filter(ProductoProveedor.proveedor_id == provider_id.upper()).all()}
        
        # Guardaremos los registros nuevos y los actualizaremos
        for _, row in df.iterrows():
            sku = row['sku_proveedor']
            nombre = row['nombre_original']
            precio_crudo = row['precio_crudo']
            barcode = row['codigo_barras']
            if pd.isna(barcode) or barcode == "":
                barcode = None
                
            # Calcular costo aplicando la cascada
            costo_calculado = calculate_cost_cascade(precio_crudo, provider_id.upper(), config)
            
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
                p_prov.last_imported_at = datetime.utcnow()
                imported_count += 1
            else:
                # Insertar nuevo
                new_prov_prod = ProductoProveedor(
                    proveedor_id=provider_id.upper(),
                    sku_proveedor=sku,
                    nombre_original=nombre,
                    precio_crudo=precio_crudo,
                    costo_calculado=costo_calculado,
                    stock_crudo=10,  # Valor de stock inicial por defecto o calculado
                    codigo_barras=barcode,
                    estado_unificacion='PENDIENTE'
                )
                session.add(new_prov_prod)
                imported_count += 1
                
        session.commit()
        logger.info(f"Importación de '{provider_id.upper()}' completada: {imported_count} filas procesadas. Cambios de precio: {price_change_count}. Alertas: {warnings_count}.")
        return imported_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error importando proveedor '{provider_id}': {e}", exc_info=True)
        raise
    finally:
        session.close()

if __name__ == "__main__":
    # Ingesta completa de proveedores configurados
    config = load_config("config.yaml")
    db_path = config.get("paths", {}).get("db_path", "data/etl_database.db")
    providers = config.get("extraction", {}).get("providers", {})
    
    for prov_name in providers.keys():
        import_supplier_data(prov_name, db_path=db_path)

import os
import re
import pandas as pd
from sqlalchemy.orm import Session
from src.utils.logger import setup_logger
from src.utils.helpers import load_config
from src.models import init_db, get_db_session, CatalogoMaestro

logger = setup_logger()

def extract_brand_from_name(name: str) -> str:
    """
    Intenta extraer la marca a partir del nombre del producto usando palabras clave comunes.
    """
    name_upper = name.upper()
    brands = ["BIC", "ROTRING", "DELI", "KANGARO", "FILGO", "PLANTEC", "POWERLAND", "PIZZINI", "FABER-CASTELL", "FABER", "SIMBALL", "EBR"]
    for brand in brands:
        if re.search(r'\b' + re.escape(brand) + r'\b', name_upper):
            return brand
    return "VARIOS"

def generate_mock_woocommerce_csv(target_path: str) -> None:
    """
    Genera un archivo CSV simulado con la estructura típica de WooCommerce 
    si no existe en el sistema, para permitir pruebas inmediatas.
    """
    if os.path.exists(target_path):
        return

    logger.info(f"Archivo WooCommerce CSV no encontrado. Generando archivo simulado en: {target_path}")
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    mock_data = [
        {"ID": 1001, "SKU": "ALE-2240010", "Name": "Abecedario Eva Magic Completo x 52 Unidades", "Regular price": 4738.00, "Meta: _wcb_barcode": "7798071680551"},
        {"ID": 1002, "SKU": "PL-2", "Name": "Combo 3 Kit Powerland", "Regular price": 815722.00, "Meta: _wcb_barcode": ""},
        {"ID": 1003, "SKU": "PL-201", "Name": "Fichas Para Abacos x 50 Un. Powerland", "Regular price": 10533.00, "Meta: _wcb_barcode": ""},
        {"ID": 1004, "SKU": "ALE-1520408", "Name": "Abrochadora Deli Animales Mini Nº 10", "Regular price": 7246.00, "Meta: _wcb_barcode": "6921734904522"},
        {"ID": 1005, "SKU": "WC-MOCK99", "Name": "Producto Exclusivo De Web", "Regular price": 1400.00, "Meta: _wcb_barcode": "999888777666"}
    ]
    
    df = pd.DataFrame(mock_data)
    df.to_csv(target_path, index=False, encoding='utf-8')
    logger.info("CSV simulado generado con éxito.")

def clean_float(val) -> float:
    """
    Limpia y convierte a float un valor numérico.
    """
    if pd.isna(val) or val == "":
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def clean_string_code(val) -> str:
    """
    Limpia y convierte a string un código numérico o alfanumérico.
    Elimina sufijos decimales (.0) y espacios vacíos.
    """
    if pd.isna(val) or val == "":
        return ""
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
    val_str = str(val).strip()
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    return val_str

def migrate_woocommerce_csv(csv_path: str, db_path: str = None) -> int:
    """
    Lee el CSV de WooCommerce e inserta/actualiza todos los registros 
    en el Catálogo Maestro (Base de Datos SQLite).
    """
    logger.info(f"Iniciando migración desde WooCommerce CSV: {csv_path}")
    
    # 1. Asegurar que existe el archivo CSV
    generate_mock_woocommerce_csv(csv_path)
    
    # 2. Cargar CSV a DataFrame
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
    except Exception as e:
        logger.warning(f"Error cargando con UTF-8 ({e}). Reintentando con ISO-8859-1...")
        df = pd.read_csv(csv_path, encoding='ISO-8859-1')
        
    logger.info(f"CSV cargado. Registros encontrados en archivo: {len(df)}")
    
    # 3. Inicializar DB si no está inicializada
    init_db(db_path)
    SessionClass = get_db_session(db_path)
    session: Session = SessionClass()
    
    # Mapeo flexible de columnas
    col_mapping = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if col_lower in ['id', 'id_woocommerce']:
            col_mapping['id'] = col
        elif col_lower in ['sku', 'sku_interno']:
            col_mapping['sku'] = col
        elif col_lower in ['name', 'nombre', 'title', 'título']:
            col_mapping['nombre'] = col
        elif col_lower in ['regular price', 'regular_price', 'precio normal', 'precio_normal', 'precio']:
            col_mapping['precio_venta'] = col
        elif col_lower in ['meta: _wcb_barcode', 'barcode', 'código de barras', 'codigo_barras', 'codigo de barras', 'barras']:
            col_mapping['barcode'] = col
            
    logger.info(f"Mapeo de columnas WooCommerce: {col_mapping}")
    
    sku_col = col_mapping.get('sku')
    nombre_col = col_mapping.get('nombre')
    id_col = col_mapping.get('id')
    price_col = col_mapping.get('precio_venta')
    barcode_col = col_mapping.get('barcode')
    
    inserted_count = 0
    updated_count = 0
    
    try:
        for index, row in df.iterrows():
            # Obtener y validar el SKU
            raw_sku = row.get(sku_col) if sku_col else None
            if pd.isna(raw_sku) or str(raw_sku).strip() == "":
                raw_id = row.get(id_col) if id_col else None
                if not pd.isna(raw_id):
                    sku = f"WC-{int(raw_id)}"
                else:
                    logger.warning(f"Fila {index} omitida: SKU e ID no válidos.")
                    continue
            else:
                sku = str(raw_sku).strip()
                
            # Obtener datos básicos
            nombre = str(row.get(nombre_col)).strip().upper() if nombre_col and not pd.isna(row.get(nombre_col)) else "PRODUCTO SIN NOMBRE"
            id_wc = int(row.get(id_col)) if id_col and not pd.isna(row.get(id_col)) else None
            barcode = clean_string_code(row.get(barcode_col)) if barcode_col else ""
            if barcode == "":
                barcode = None
                
            precio_venta = clean_float(row.get(price_col)) if price_col else 0.0
            margen = 0.40  # Margen por defecto
            costo = round(precio_venta / (1 + margen), 2)
            
            # Detectar marca y categoria
            marca = extract_brand_from_name(nombre)
            # Definir categoria por defecto o extraer de columna si existiera
            categoria = "VARIOS"
            
            # Buscar en catalogo_maestro
            db_product = session.query(CatalogoMaestro).filter(CatalogoMaestro.master_sku == sku).first()
            
            if db_product:
                db_product.nombre_normalizado = nombre
                if barcode:
                    db_product.codigo_barras = barcode
                if id_wc:
                    db_product.id_woocommerce = id_wc
                db_product.precio_venta = precio_venta
                db_product.marca = marca
                if db_product.precio_costo == 0.0 or db_product.precio_costo is None:
                    db_product.precio_costo = costo
                updated_count += 1
            else:
                new_product = CatalogoMaestro(
                    master_sku=sku,
                    codigo_barras=barcode,
                    nombre_normalizado=nombre,
                    marca=marca,
                    categoria=categoria,
                    precio_costo=costo,
                    margen_ganancia=margen,
                    precio_venta=precio_venta,
                    id_woocommerce=id_wc
                )
                session.add(new_product)
                inserted_count += 1
                
        session.commit()
        logger.info(f"Migración WooCommerce completada. Insertados: {inserted_count}, Actualizados: {updated_count}")
        return inserted_count + updated_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error en migración WooCommerce: {e}", exc_info=True)
        raise
    finally:
        session.close()

if __name__ == "__main__":
    config = load_config("config.yaml")
    csv_path = config.get("paths", {}).get("woocommerce_csv_path", "data/raw/woocommerce_products.csv")
    db_path = config.get("paths", {}).get("db_path", "data/etl_database.db")
    migrate_woocommerce_csv(csv_path, db_path)

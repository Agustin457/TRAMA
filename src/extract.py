import os
import pandas as pd
from src.utils.logger import setup_logger

logger = setup_logger()

def clean_string_code(val) -> str:
    """
    Normaliza un código a string limpio sin decimales (.0) ni espacios.
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

def clean_price(val) -> float:
    """
    Limpia y convierte a float valores de precio de proveedores.
    Soporta formatos numéricos directos y strings con formato monetario
    local (ej. "$ 2.960,79" o "815722.0").
    """
    if pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
        
    s = str(val).strip().replace('$', '').replace(' ', '')
    
    # Manejar formatos argentinos (ej: 2.960,79 o 1.250,5)
    if ',' in s:
        s = s.replace('.', '')     # Quitar puntos de miles
        s = s.replace(',', '.')     # Convertir coma decimal a punto
        
    try:
        return float(s)
    except ValueError:
        logger.warning(f"No se pudo parsear el precio: '{val}'. Se asigna 0.0.")
        return 0.0

def extract_ale(file_path: str, sheet_name: str = "LISTA DE PRECIOS", header_row: int = 2) -> pd.DataFrame:
    """
    Extrae y estandariza los datos del archivo Excel del proveedor ALE.
    Columnas del Excel esperadas: ['Codigo', 'Descripción', 'Precio', 'Fecha', 'Barra', ...]
    """
    logger.info(f"Extrayendo datos de ALE desde {file_path}")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo de ALE en: {file_path}")
        
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
    logger.info(f"ALE: {len(df)} filas crudas leídas.")
    
    # Estandarizar nombres de columnas
    df.columns = [str(c).strip() for c in df.columns]
    
    # Mapeo de columnas
    rename_cols = {
        'Codigo': 'sku_proveedor',
        'Descripción': 'nombre_original',
        'Precio': 'precio_crudo',
        'Barra': 'codigo_barras'
    }
    
    # Validar que existan las columnas necesarias
    for col_req in ['Codigo', 'Descripción', 'Precio']:
        if col_req not in df.columns:
            # Buscar coincidencia flexible por si acaso
            found = False
            for col_act in df.columns:
                if col_req.lower() in col_act.lower():
                    rename_cols[col_act] = rename_cols.get(col_req, col_req.lower())
                    found = True
                    break
            if not found and col_req != 'Barra':
                raise ValueError(f"Falta columna requerida '{col_req}' en la lista de ALE. Columnas actuales: {df.columns.tolist()}")
                
    df_clean = df.rename(columns=rename_cols)
    
    # Conservar solo columnas necesarias
    cols_to_keep = ['sku_proveedor', 'nombre_original', 'precio_crudo', 'codigo_barras']
    for col in cols_to_keep:
        if col not in df_clean.columns:
            df_clean[col] = None
            
    df_clean = df_clean[cols_to_keep].copy()
    
    # Limpieza de registros
    df_clean['sku_proveedor'] = df_clean['sku_proveedor'].apply(clean_string_code)
    df_clean['codigo_barras'] = df_clean['codigo_barras'].apply(clean_string_code)
    df_clean['precio_crudo'] = df_clean['precio_crudo'].apply(clean_price)
    
    # Remover filas vacías o cabeceras duplicadas
    df_clean = df_clean.dropna(subset=['sku_proveedor', 'nombre_original'], how='all')
    df_clean = df_clean[df_clean['sku_proveedor'] != ""]
    df_clean = df_clean[~df_clean['sku_proveedor'].str.lower().str.contains('codigo|código')]
    
    # Eliminar espacios extras del título
    df_clean['nombre_original'] = df_clean['nombre_original'].astype(str).str.strip().str.upper()
    df_clean['proveedor_id'] = 'ALE'
    
    logger.info(f"ALE: {len(df_clean)} registros estandarizados.")
    return df_clean

def extract_powerland(file_path: str, sheet_name: str = "Lista de precios de productos", header_row: int = 5) -> pd.DataFrame:
    """
    Extrae y estandariza los datos del archivo Excel del proveedor Powerland.
    Columnas del Excel esperadas: ['Código', nan (Descripción), 'Precio']
    """
    logger.info(f"Extrayendo datos de Powerland desde {file_path}")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo de Powerland en: {file_path}")
        
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
    logger.info(f"Powerland: {len(df)} filas crudas leídas.")
    
    # En Powerland la segunda columna a veces no tiene nombre y pandas la lee como Unnamed: 1 o Unnamed: 2.
    # Vamos a forzar el nombramiento por índice si las columnas son 3
    if len(df.columns) >= 3:
        # Renombramos por posición
        df.columns = ['Código', 'Descripción', 'Precio'] + list(df.columns[3:])
    
    df.columns = [str(c).strip() for c in df.columns]
    
    # Mapeo de columnas
    rename_cols = {
        'Código': 'sku_proveedor',
        'Descripción': 'nombre_original',
        'Precio': 'precio_crudo'
    }
    
    # Validar que existan las columnas necesarias
    for col_req in ['Código', 'Descripción', 'Precio']:
        if col_req not in df.columns:
            raise ValueError(f"Falta columna requerida '{col_req}' en la lista de Powerland. Columnas actuales: {df.columns.tolist()}")
            
    df_clean = df.rename(columns=rename_cols)
    
    # Conservar solo columnas necesarias
    df_clean['codigo_barras'] = None
    cols_to_keep = ['sku_proveedor', 'nombre_original', 'precio_crudo', 'codigo_barras']
    df_clean = df_clean[cols_to_keep].copy()
    
    # Limpieza de registros
    df_clean['sku_proveedor'] = df_clean['sku_proveedor'].apply(clean_string_code)
    df_clean['precio_crudo'] = df_clean['precio_crudo'].apply(clean_price)
    
    # Remover filas vacías
    df_clean = df_clean.dropna(subset=['sku_proveedor', 'nombre_original'], how='all')
    df_clean = df_clean[df_clean['sku_proveedor'] != ""]
    df_clean = df_clean[~df_clean['sku_proveedor'].str.lower().str.contains('codigo|código')]
    
    df_clean['nombre_original'] = df_clean['nombre_original'].astype(str).str.strip().str.upper()
    df_clean['proveedor_id'] = 'POWERLAND'
    
    logger.info(f"Powerland: {len(df_clean)} registros estandarizados.")
    return df_clean

def extract_rotring(file_path: str, sheet_name: str = "Hoja1", header_row: int = 17) -> pd.DataFrame:
    """
    Extrae y estandariza los datos del archivo Excel del proveedor Rotring/Plantec.
    Columnas del Excel esperadas: ['CODIGO', 'DESCRIPCION', 'UNITARIO EN PESOS', 'PRESENTACIÓN', 'EMBALAJE', 'OBSERVACIONES', 'CODIGO DE BARRAS']
    """
    logger.info(f"Extrayendo datos de Rotring desde {file_path}")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo de Rotring en: {file_path}")
        
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
    logger.info(f"Rotring: {len(df)} filas crudas leídas.")
    
    df.columns = [str(c).strip() for c in df.columns]
    
    # Mapeo de columnas
    rename_cols = {
        'CODIGO': 'sku_proveedor',
        'DESCRIPCION': 'nombre_original',
        'UNITARIO EN PESOS': 'precio_crudo',
        'CODIGO DE BARRAS': 'codigo_barras'
    }
    
    # Validar que existan las columnas necesarias
    for col_req in ['CODIGO', 'DESCRIPCION', 'UNITARIO EN PESOS']:
        if col_req not in df.columns:
            # Buscar por si acaso
            found = False
            for col_act in df.columns:
                if col_req.lower() in col_act.lower():
                    rename_cols[col_act] = rename_cols.get(col_req, col_req.lower())
                    found = True
                    break
            if not found:
                raise ValueError(f"Falta columna requerida '{col_req}' en la lista de Rotring. Columnas actuales: {df.columns.tolist()}")
                
    df_clean = df.rename(columns=rename_cols)
    
    # Conservar solo columnas necesarias
    cols_to_keep = ['sku_proveedor', 'nombre_original', 'precio_crudo', 'codigo_barras']
    for col in cols_to_keep:
        if col not in df_clean.columns:
            df_clean[col] = None
            
    df_clean = df_clean[cols_to_keep].copy()
    
    # Limpieza de registros
    df_clean['sku_proveedor'] = df_clean['sku_proveedor'].apply(clean_string_code)
    df_clean['codigo_barras'] = df_clean['codigo_barras'].apply(clean_string_code)
    df_clean['precio_crudo'] = df_clean['precio_crudo'].apply(clean_price)
    
    # Remover filas vacías y filas de títulos de sección (que no tienen precio)
    df_clean = df_clean.dropna(subset=['sku_proveedor', 'nombre_original'], how='all')
    df_clean = df_clean[df_clean['sku_proveedor'] != ""]
    df_clean = df_clean[~df_clean['sku_proveedor'].str.lower().str.contains('codigo|código')]
    
    # IMPORTANTE: En Rotring, los títulos de categorías vienen con precio cero o nulo.
    # Los removemos para mantener solo productos vendibles
    df_clean = df_clean[df_clean['precio_crudo'] > 0.0]
    
    df_clean['nombre_original'] = df_clean['nombre_original'].astype(str).str.strip().str.upper()
    df_clean['proveedor_id'] = 'ROTRING'
    
    logger.info(f"Rotring: {len(df_clean)} registros estandarizados.")
    return df_clean

def extract_all_providers(config_path: str = "config.yaml") -> pd.DataFrame:
    """
    Lee y concatena todos los proveedores configurados.
    """
    from src.utils.helpers import load_config
    config = load_config(config_path)
    
    raw_dir = config.get("paths", {}).get("raw_data_dir", "data/raw")
    providers = config.get("extraction", {}).get("providers", {})
    
    dfs = []
    
    if "ale" in providers:
        cfg = providers["ale"]
        f_path = os.path.join(raw_dir, cfg["filename"])
        dfs.append(extract_ale(f_path, sheet_name=cfg["sheet"], header_row=cfg["header_row"]))
        
    if "powerland" in providers:
        cfg = providers["powerland"]
        f_path = os.path.join(raw_dir, cfg["filename"])
        dfs.append(extract_powerland(f_path, sheet_name=cfg["sheet"], header_row=cfg["header_row"]))
        
    if "rotring" in providers:
        cfg = providers["rotring"]
        f_path = os.path.join(raw_dir, cfg["filename"])
        dfs.append(extract_rotring(f_path, sheet_name=cfg["sheet"], header_row=cfg["header_row"]))
        
    if dfs:
        df_all = pd.concat(dfs, ignore_index=True)
        logger.info(f"Total registros unificados de extracción: {len(df_all)}")
        return df_all
    else:
        logger.warning("No se configuró ningún proveedor para extracción.")
        return pd.DataFrame()

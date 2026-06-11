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
        return 0.0

def clean_description(raw_name) -> str:
    """
    Convierte el valor crudo de la columna DESCRIPCION a un string limpio.
    Maneja el caso de descripciones numéricas (ej: talles de pincel 0, 1, 2, 3/0)
    que pandas puede leer como float (0.0, 1.0...).
    """
    if pd.isna(raw_name):
        return ""
    # Si es float y es entero exacto (ej: 0.0, 1.0, 3.0), convertir a int string
    if isinstance(raw_name, float):
        if raw_name.is_integer():
            return str(int(raw_name))
        else:
            return str(raw_name).strip()
    # Si es int
    if isinstance(raw_name, int):
        return str(raw_name)
    # Si es string
    return str(raw_name).strip()

def find_header_row(file_path: str, sheet_name: str) -> int:
    """
    Escanea las primeras 100 filas de una hoja de cálculo para encontrar
    la fila que contiene la cabecera (identificada por tener 'codigo' o 'código').
    """
    df = pd.read_excel(file_path, sheet_name=sheet_name, nrows=100, header=None)
    for idx, row in df.iterrows():
        vals = [str(v).strip().lower() for v in row.dropna()]
        if any('codigo' in v or 'código' in v or 'cod' in v for v in vals):
            logger.info(f"Fila de cabecera detectada en fila {idx} para {file_path}")
            return idx
    # Fallback si no se encuentra
    logger.warning(f"No se pudo detectar automáticamente la cabecera en {file_path}, usando fila 0 por defecto.")
    return 0

def extract_standardized_df(file_path: str, sheet_name: str, provider_id: str) -> pd.DataFrame:
    """
    Extrae de forma dinámica y estandariza cualquier archivo de proveedor,
    detectando automáticamente la fila de cabecera y el mapeo de columnas.
    Para el proveedor ROTRING (Plantec), aplica lógica jerárquica:
    - Fila sin precio + descripción de texto → producto padre (guarda descripción como contexto)
    - Fila con SKU + precio → variación; el nombre completo = descripción padre + descripción variación
    - Fila sin SKU → cabecera de sección, resetea el contexto padre
    """
    logger.info(f"Iniciando extracción estandarizada de {provider_id} desde {file_path} (Hoja: {sheet_name})")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo de {provider_id} en: {file_path}")
        
    header_row = find_header_row(file_path, sheet_name)
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
    
    # Estandarizar nombres de columnas a minúsculas
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    # Mapear columnas dinámicamente.
    # IMPORTANTE: detectar barcode ANTES de SKU, porque 'codigo de barras'
    # contiene la palabra 'codigo' y si el SKU se evalúa primero el elif
    # del barcode nunca se alcanza.
    col_mapping = {}
    for col in df.columns:
        # 1) Barcode — tiene prioridad para evitar conflicto con 'codigo'
        #    Cubre: 'codigo de barras', 'barcode', 'barra' (Lista Ale), 'ean'
        if 'barras' in col or 'barcode' in col or col == 'barra' or col == 'ean':
            col_mapping['codigo_barras'] = col
        # 2) SKU — solo si no contiene 'barras'/'barcode'
        #    'sku' es el nombre estándar usado por los archivos preprocesados
        elif (col == 'sku' or 'codigo' in col or 'código' in col or col == 'cod') and 'barras' not in col and 'barcode' not in col:
            col_mapping['sku_proveedor'] = col
        # 3) Nombre / descripción
        elif 'descripcion' in col or 'descripción' in col or col in ['nombre', 'detalle', 'producto', 'unnamed: 1']:
            if 'nombre_original' not in col_mapping:
                col_mapping['nombre_original'] = col
        # 4) Precio
        elif 'precio' in col or 'pesos' in col or col == 'lista' or col == 'lista 1' or col == 'unitario':
            if 'precio_crudo' not in col_mapping:
                col_mapping['precio_crudo'] = col
            
    # Fallback para nombre_original (por ejemplo, columnas sin nombre que lee pandas)
    if 'nombre_original' not in col_mapping:
        for col in df.columns:
            if 'unnamed: 1' in col or 'unnamed: 2' in col:
                col_mapping['nombre_original'] = col
                break
                
    sku_col = col_mapping.get('sku_proveedor')
    name_col = col_mapping.get('nombre_original')
    price_col = col_mapping.get('precio_crudo')
    barcode_col = col_mapping.get('codigo_barras')
    
    logger.info(f"Mapeo de columnas detectado: {col_mapping}")
    if barcode_col:
        logger.info(f"Columna de código de barras detectada: '{barcode_col}'")
    else:
        logger.info("Este archivo no tiene columna de código de barras.")
    
    # Si falla la detección, forzar por orden típico
    if not sku_col or not name_col:
        logger.warning(f"Fallo en detección automática de columnas en {file_path}. Aplicando orden de fallback.")
        if len(df.columns) >= 3:
            # Forzar primera columna como SKU, segunda como Nombre, tercera como Precio
            sku_col, name_col, price_col = df.columns[0], df.columns[1], df.columns[2]
        else:
            raise ValueError(f"No se pudieron encontrar columnas válidas en {file_path}. Columnas: {df.columns.tolist()}")
            
    raw_rows = []
    current_parent_description = ""
    
    for _, row in df.iterrows():
        raw_sku = row.get(sku_col)
        sku = clean_string_code(raw_sku)
        
        # Usar clean_description para manejar valores numéricos (talles de pincel, etc.)
        raw_name = row.get(name_col)
        name = clean_description(raw_name)
        
        raw_price_val = row.get(price_col) if price_col else None
        price = clean_price(raw_price_val)
        
        raw_barcode = row.get(barcode_col) if barcode_col else None
        barcode = clean_string_code(raw_barcode) if raw_barcode is not None and not pd.isna(raw_barcode) else None
        if barcode == "":
            barcode = None
            
        # Omitir filas completamente vacías
        if not sku and not name:
            continue
            
        # Omitir cabeceras de tabla repetidas
        if sku.lower() in ['codigo', 'código', 'cod']:
            continue
            
        if provider_id.upper() == "ROTRING":
            # Si no tiene SKU pero tiene nombre → cabecera de sección: resetear contexto padre
            if not sku and name:
                current_parent_description = ""
                continue
                
            # Si tiene SKU y nombre de texto (no puramente numérico) pero precio == 0 → producto padre
            # Solo actúa como padre si la descripción es un string real (no un número aislado como "0" o "1")
            name_is_text = name and not name.replace('.', '').replace('/', '').replace('-', '').isdigit()
            if sku and name and price == 0.0 and name_is_text:
                current_parent_description = name
                logger.debug(f"Padre detectado: SKU={sku}, Desc='{name}'")
                continue
                
            # Si tiene SKU y precio > 0 → variación válida
            if sku and price > 0.0:
                # Construir nombre completo combinando padre + variación
                if current_parent_description and name:
                    full_name = f"{current_parent_description} {name}"
                elif name:
                    full_name = name
                else:
                    full_name = f"PRODUCTO {sku}"
                    
                raw_rows.append({
                    'sku_proveedor': sku,
                    'nombre_original': full_name.strip().upper(),
                    'precio_crudo': price,
                    'codigo_barras': barcode,
                    'proveedor_id': provider_id.upper()
                })
        else:
            # Comportamiento estándar para otros proveedores (ALE, POWERLAND)
            if sku and name and price > 0.0:
                raw_rows.append({
                    'sku_proveedor': sku,
                    'nombre_original': name.strip().upper(),
                    'precio_crudo': price,
                    'codigo_barras': barcode,
                    'proveedor_id': provider_id.upper()
                })
                
    if raw_rows:
        df_clean = pd.DataFrame(raw_rows)
    else:
        df_clean = pd.DataFrame(columns=['sku_proveedor', 'nombre_original', 'precio_crudo', 'codigo_barras', 'proveedor_id'])
        
    logger.info(f"Extracción exitosa para {provider_id}. Registros válidos: {len(df_clean)}")
    return df_clean

def extract_ale(file_path: str, sheet_name: str = "LISTA DE PRECIOS", header_row: int = 2) -> pd.DataFrame:
    return extract_standardized_df(file_path, sheet_name, "ALE")

def extract_powerland(file_path: str, sheet_name: str = "Lista de precios de productos", header_row: int = 5) -> pd.DataFrame:
    return extract_standardized_df(file_path, sheet_name, "POWERLAND")

def extract_rotring(file_path: str, sheet_name: str = "Hoja1", header_row: int = 17) -> pd.DataFrame:
    return extract_standardized_df(file_path, sheet_name, "ROTRING")

def extract_all_providers(config_path: str = "config.yaml") -> pd.DataFrame:
    """
    Lee y concatena todos los proveedores configurados.
    """
    from src.utils.helpers import load_config
    import glob
    
    config = load_config(config_path)
    raw_dir = config.get("paths", {}).get("raw_data_dir", "data/raw")
    providers = config.get("extraction", {}).get("providers", {})
    
    dfs = []
    
    for provider_id, cfg in providers.items():
        pattern = os.path.join(raw_dir, cfg["filename"])
        matching_files = glob.glob(pattern)
        
        for f_path in matching_files:
            dfs.append(extract_standardized_df(f_path, sheet_name=cfg["sheet"], provider_id=provider_id.upper()))
            
    if dfs:
        df_all = pd.concat(dfs, ignore_index=True)
        logger.info(f"Total registros unificados de extracción: {len(df_all)}")
        return df_all
    else:
        logger.warning("No se configuró ningún proveedor para extracción.")
        return pd.DataFrame()

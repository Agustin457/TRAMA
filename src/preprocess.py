"""
preprocess.py
Normaliza cada lista de precios a 4 columnas estandarizadas:
    sku | nombre | precio | codigo_barras

Los archivos normalizados se guardan en data/processed/ con el sufijo _normalizado.xlsx
y son la fuente de datos que usa el pipeline ETL en lugar de los archivos raw originales.
"""

import re
import os
import warnings
import pandas as pd
from src.utils.logger import setup_logger

warnings.filterwarnings("ignore")

logger = setup_logger()

# ─────────────────────────────────────────────
# Helpers de normalización
# ─────────────────────────────────────────────

def normalize_col_name(s):
    """Lowercase, sin tildes, sin espacios extras."""
    if not isinstance(s, str):
        s = str(s)
    s = s.lower().strip()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        s = s.replace(a, b)
    return s


def detect_column(columns, patterns):
    """Devuelve el primer nombre de columna que matchea alguno de los patrones."""
    for col in columns:
        n = normalize_col_name(col)
        for pat in patterns:
            if re.search(pat, n):
                return col
    return None


def find_header_row(df_raw, keywords=("codigo", "descripcion", "precio", "sku", "nombre", "barras")):
    """Busca la fila que más columnas-keyword tiene y la devuelve como índice."""
    best_row, best_score = 0, 0
    for i, row in df_raw.iterrows():
        score = sum(
            any(k in normalize_col_name(str(v)) for k in keywords)
            for v in row
        )
        if score > best_score:
            best_score, best_row = score, i
    return best_row if best_score >= 2 else None


def build_dataframe(df_raw, header_row):
    """Re-construye el DataFrame usando header_row como encabezado."""
    new_cols = df_raw.iloc[header_row].tolist()
    df = df_raw.iloc[header_row + 1:].copy()
    df.columns = new_cols
    df = df.reset_index(drop=True)
    return df


def clean_origin(text):
    """
    Elimina menciones de origen o país (ej. 'Industria Argentina', 'Made in Italy',
    'Importado', 'Nacional') de la descripción del producto.
    """
    if pd.isna(text) or not isinstance(text, str):
        return text
    
    # 1. Eliminar patrones de industria/made in/origen + pais/nacion (incluye abreviaciones)
    pat_keyword = re.compile(r'\b(industria|ind\.?|made(?:\s*in)?|origen|orig\.?)\s+[a-zñáéíóúü]+\b', re.IGNORECASE)
    text = pat_keyword.sub('', text)
    
    # 2. Eliminar palabras sueltas como importado, nacional, etc.
    pat_standalone = re.compile(r'\b(importado|nacional|importados|nacionales)\b', re.IGNORECASE)
    text = pat_standalone.sub('', text)
    
    # 3. Limpiar guiones y espacios residuales
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'^\s*[-–—]\s*', '', text)
    text = re.sub(r'\s*[-–—]\s*$', '', text)
    text = re.sub(r'\s*[-–—]\s*[-–—]\s*', ' - ', text)
    text = re.sub(r'\s*[-–—]\s*$', '', text)
    
    return text.strip()


def remove_duplicate_words_hierarchical(parts):
    """
    Deduplica palabras repetidas jerárquicamente de izquierda a derecha.
    Si una parte empieza con una palabra (o raíz) que ya apareció en una parte previa,
    se elimina esa palabra inicial de la parte actual para evitar redundancias.
    """
    cleaned_parts = []
    seen_words = set()
    
    for part in parts:
        if not isinstance(part, str):
            part = str(part)
        part = part.strip()
        if not part:
            continue
            
        words = part.split()
        if not words:
            continue
            
        def norm_word(w):
            w = w.lower().strip(".,()[]-")
            for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
                w = w.replace(a, b)
            return w
            
        cleaned_words = []
        skip_mode = True
        
        for w in words:
            nw = norm_word(w)
            # Si es conector o preposición corta, no remover
            if len(nw) <= 2 or nw in ("con", "sin", "para", "de", "por", "del", "en"):
                cleaned_words.append(w)
                continue
                
            is_duplicate = False
            for seen in seen_words:
                # Caso 1: Coincidencia exacta
                if nw == seen:
                    is_duplicate = True
                    break
                # Caso 2: Prefijo/sufijo muy similar (ej: compas vs compases)
                if (nw.startswith(seen) and len(nw) - len(seen) <= 2) or (seen.startswith(nw) and len(seen) - len(nw) <= 2):
                    is_duplicate = True
                    break
                # Caso 3: Raíz común de 5 o más letras (ej: acrilico vs acrilica)
                if len(nw) >= 5 and len(seen) >= 5 and nw[:5] == seen[:5]:
                    is_duplicate = True
                    break
                    
            if skip_mode and is_duplicate:
                continue
            else:
                skip_mode = False
                cleaned_words.append(w)
                seen_words.add(nw)
                
        cleaned_part = " ".join(cleaned_words).strip()
        # Limpiar conectores de los bordes
        cleaned_part = re.sub(r'^\s*[-–—]\s*', '', cleaned_part)
        cleaned_part = re.sub(r'\s*[-–—]\s*$', '', cleaned_part)
        if cleaned_part:
            cleaned_parts.append(cleaned_part)
            
    return cleaned_parts


def is_price(val):
    """True si el valor parece un precio numérico positivo."""
    if pd.isna(val) or val == "":
        return False
    if isinstance(val, (int, float)):
        return float(val) > 0
    try:
        s = str(val).strip().replace('$', '').replace(' ', '')
        if ',' in s:
            s = s.replace('.', '')
            s = s.replace(',', '.')
        f = float(s)
        return f > 0
    except Exception:
        return False


def clean_price(val):
    """Convierte a float limpio; None si no es un precio válido."""
    if pd.isna(val) or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val) if float(val) > 0 else None
    try:
        s = str(val).strip().replace('$', '').replace(' ', '')
        if ',' in s:
            s = s.replace('.', '')
            s = s.replace(',', '.')
        f = float(s)
        return f if f > 0 else None
    except Exception:
        return None


def clean_barcode(val):
    """Devuelve el código de barras como string sin decimales ni espacios."""
    if pd.isna(val) or str(val).strip() in ("", "nan", "None"):
        return None
    try:
        return str(int(float(str(val).strip())))
    except Exception:
        s = str(val).strip()
        digits = re.sub(r"\D", "", s)
        return digits if len(digits) >= 8 else (s if s else None)


# ─────────────────────────────────────────────
# Patrones de detección de columnas
# ─────────────────────────────────────────────

SKU_PATS    = [r"\bsku\b", r"cod(ig)?o?\b", r"ref(erencia)?", r"art(iculo)?", r"\bitem\b", r"prov"]
NOMBRE_PATS = [r"nombre", r"descri", r"producto", r"detalle", r"articulo", r"\bitem\b"]
PRECIO_PATS = [r"precio", r"unit", r"pesos", r"p\.?v\.?p", r"importe", r"valor", r"costo"]
BARRA_PATS  = [r"barra", r"\bean\b", r"gtin", r"upc", r"cod.*bar"]


# ─────────────────────────────────────────────
# Procesadores por proveedor
# ─────────────────────────────────────────────

def process_generic(df_raw, filename=""):
    """
    Estrategia general (fallback):
    1. Encuentra la fila de encabezado automáticamente.
    2. Mapea columnas por nombre usando los patrones.
    """
    header_row = find_header_row(df_raw)
    if header_row is None:
        logger.warning(f"No se encontró encabezado válido en {filename}")
        return None

    df = build_dataframe(df_raw, header_row)
    df.dropna(how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    cols = df.columns.tolist()
    sku_col    = detect_column(cols, SKU_PATS)
    nombre_col = detect_column(cols, NOMBRE_PATS)
    precio_col = detect_column(cols, PRECIO_PATS)
    barra_col  = detect_column(cols, BARRA_PATS)

    logger.info(f"  Generic → SKU='{sku_col}' | Nombre='{nombre_col}' | Precio='{precio_col}' | Barras='{barra_col}'")

    result = pd.DataFrame()
    result["sku"]           = df[sku_col].astype(str).str.strip() if sku_col else None
    result["nombre"]        = df[nombre_col].astype(str).str.strip() if nombre_col else None
    result["precio"]        = df[precio_col].apply(clean_price) if precio_col else None
    result["codigo_barras"] = df[barra_col].apply(clean_barcode) if barra_col else None

    return result


def process_ale(filepath):
    """
    Lista Ale — intenta la hoja 'LISTA DE PRECIOS (2)' (más limpia con columnas
    exactas: sku_ale | nombre | precio | codigo de barras).
    Fallback automático a 'LISTA DE PRECIOS' con detección dinámica si la hoja (2) no existe.
    El precio incluye IVA.
    """
    logger.info(f"Preprocesando {os.path.basename(filepath)}")

    try:
        # Hoja secundaria con columnas ya conocidas
        df = pd.read_excel(filepath, sheet_name="LISTA DE PRECIOS (2)", header=0)
        df.columns = [normalize_col_name(str(c)) for c in df.columns]

        result = pd.DataFrame()
        result["sku"]           = df["sku_ale"].astype(str).str.strip()
        result["nombre"]        = df["nombre"].astype(str).str.strip()
        result["precio"]        = df["precio"].apply(clean_price)
        result["codigo_barras"] = df["codigo de barras"].apply(clean_barcode)

    except Exception:
        # Fallback: hoja principal con detección automática de encabezado y columnas
        logger.warning("  Hoja 'LISTA DE PRECIOS (2)' no encontrada, usando fallback dinámico")
        try:
            df_raw = pd.read_excel(filepath, header=None, sheet_name="LISTA DE PRECIOS")
        except Exception:
            df_raw = pd.read_excel(filepath, header=None, sheet_name=0)

        header_row = find_header_row(df_raw)
        if header_row is None:
            logger.warning(f"No se encontró encabezado en {os.path.basename(filepath)}")
            return None

        df = build_dataframe(df_raw, header_row)
        df.columns = [normalize_col_name(str(c)) for c in df.columns]

        col_list   = df.columns.tolist()
        sku_col    = detect_column(col_list, SKU_PATS) or col_list[0]
        nombre_col = detect_column(col_list, NOMBRE_PATS) or (col_list[1] if len(col_list) > 1 else None)
        precio_col = detect_column(col_list, PRECIO_PATS) or (col_list[2] if len(col_list) > 2 else None)
        barra_col  = detect_column(col_list, BARRA_PATS)

        result = pd.DataFrame()
        result["sku"]           = df[sku_col].astype(str).str.strip() if sku_col else None
        result["nombre"]        = df[nombre_col].astype(str).str.strip() if nombre_col else None
        result["precio"]        = df[precio_col].apply(clean_price) if precio_col else None
        result["codigo_barras"] = df[barra_col].apply(clean_barcode) if barra_col else None

    result = result[result["nombre"].notna() & ~result["nombre"].isin(["nan", "NaN", ""])]
    result = result[result["precio"].notna()]
    result = result.reset_index(drop=True)

    logger.info(f"  ALE: {len(result)} productos normalizados")
    return result


def process_plantec1(filepath):
    """
    Lista Plantec 1 (Ordoñez Acrílicos).
    Intenta leer con header=0 esperando columnas: sku | nombre | precio $.
    Si falla, usa detección automática de encabezado con lógica jerárquica
    (padre sin precio → variaciones de color con precio).
    No tiene código de barras.
    """
    logger.info(f"Preprocesando {os.path.basename(filepath)}")

    try:
        # Intento directo: columnas conocidas en fila 0
        df = pd.read_excel(filepath, header=0)
        df.columns = [normalize_col_name(str(c)) for c in df.columns]

        result = pd.DataFrame()
        result["sku"]           = df["sku"].astype(str).str.strip()
        result["nombre"]        = df["nombre"].astype(str).str.strip()
        result["precio"]        = df["precio $"].apply(clean_price)
        result["codigo_barras"] = None

        result = result[result["precio"].notna()]
        result = result[result["nombre"].notna() & ~result["nombre"].isin(["nan", "NaN", ""])]

        if result.empty:
            raise ValueError("Sin datos con el método directo")

    except Exception:
        # Fallback: detección automática + lógica jerárquica padre→variación
        logger.warning("  Usando fallback jerárquico para Plantec 1")
        df_raw = pd.read_excel(filepath, header=None, sheet_name=0)
        header_row = find_header_row(df_raw)
        if header_row is None:
            logger.warning(f"No se encontró encabezado en {os.path.basename(filepath)}")
            return None

        df = build_dataframe(df_raw, header_row)
        df.columns = [normalize_col_name(str(c)) for c in df.columns]

        col_list   = df.columns.tolist()
        sku_col    = detect_column(col_list, SKU_PATS) or col_list[0]
        nombre_col = detect_column(col_list, NOMBRE_PATS) or (col_list[1] if len(col_list) > 1 else None)
        precio_col = detect_column(col_list, PRECIO_PATS) or (col_list[2] if len(col_list) > 2 else None)

        rows = []
        current_parent = ""
        for _, row in df.iterrows():
            raw_sku    = str(row.get(sku_col, "")).strip()
            raw_nombre = str(row.get(nombre_col, "")).strip() if nombre_col else ""
            if raw_nombre in ("nan", "NaN"):
                raw_nombre = ""
            raw_precio = clean_price(row.get(precio_col)) if precio_col else None

            if not raw_sku or raw_sku in ("nan", ""):
                continue
            if raw_precio is None and raw_nombre:
                current_parent = raw_nombre
                continue
            if raw_precio is not None:
                parts = [current_parent, raw_nombre] if current_parent else [raw_nombre]
                dedup_parts = remove_duplicate_words_hierarchical(parts)
                full_nombre = " ".join(dedup_parts)
                rows.append({"sku": raw_sku, "nombre": full_nombre.upper(),
                             "precio": raw_precio, "codigo_barras": None})

        result = pd.DataFrame(rows)

    if result is not None and not result.empty:
        result["nombre"] = result["nombre"].apply(clean_origin)

    logger.info(f"  PLANTEC-1: {len(result) if result is not None else 0} productos normalizados (sin código de barras)")
    return result if (result is not None and not result.empty) else None


def process_plantec_multipage(filepath):
    """
    Plantec 2/3/4/5 — formato catálogo con múltiples páginas dentro del mismo sheet.
    El encabezado se repite varias veces: CODIGO | DESCRIPCION | UNITARIO EN PESOS | ... | CODIGO DE BARRAS

    Rastrea tres niveles de jerarquía para construir el nombre completo del producto:
      - current_section:     col 0 con texto NO numérico → título de sección grande
      - current_subcategory: col 0 numérico sin precio   → sub-título / grupo de producto
      - producto real:       col 0 numérico con precio

    Nombre final: "Sección - Subcategoría - Descripción del producto"
    """
    logger.info(f"Preprocesando {os.path.basename(filepath)}")

    df_raw = pd.read_excel(filepath, header=None, sheet_name=0)

    # Encontrar todas las filas que sean encabezado (contienen "CODIGO" y "DESCRIPCION")
    header_rows = []
    for i, row in df_raw.iterrows():
        vals = [normalize_col_name(str(v)) for v in row]
        if any("codigo" in v for v in vals) and any("descrip" in v for v in vals):
            header_rows.append(i)

    if not header_rows:
        logger.warning(f"No se encontró encabezado en {os.path.basename(filepath)}")
        return None

    logger.info(f"  Encabezados encontrados en filas: {header_rows}")

    # Usar el primer encabezado para inferir los índices de columnas
    col_names = df_raw.iloc[header_rows[0]].tolist()

    def col_idx(pattern):
        for idx, name in enumerate(col_names):
            if re.search(pattern, normalize_col_name(str(name))):
                return idx
        return None

    idx_codigo = col_idx(r"codigo")
    idx_desc   = col_idx(r"descrip")
    idx_precio = col_idx(r"unit|precio")
    idx_barras = col_idx(r"barra|ean")

    # Recolectar datos rastreando tres niveles de contexto
    skip_set = set(header_rows)
    all_rows = []

    current_section     = ""   # Título de sección (col 0 texto, sin código numérico)
    current_subcategory = ""   # Sub-título (col 0 numérico, sin precio)

    for i, row in df_raw.iterrows():
        if i in skip_set:
            continue

        vals = row.tolist()

        # Saltar filas completamente vacías
        non_nan = [v for v in vals if pd.notna(v) and str(v).strip() != ""]
        if not non_nan:
            continue

        col0_raw = vals[idx_codigo] if idx_codigo is not None else None
        col0     = str(col0_raw).strip() if pd.notna(col0_raw) else ""
        desc     = str(vals[idx_desc]).strip() if idx_desc is not None and pd.notna(vals[idx_desc]) else ""
        precio_val  = vals[idx_precio] if idx_precio is not None else None
        tiene_precio = is_price(precio_val)

        # ── Col 0 vacío: ruido (footer, contacto, aviso legal) → saltar ──
        if col0 == "":
            continue

        is_numeric_code = bool(re.match(r"^[\d\.\-]+$", col0.replace(" ", "")))

        # ── Col 0 con texto NO numérico: título de sección grande ──
        if not is_numeric_code:
            current_section     = col0.strip()
            current_subcategory = ""   # Resetear sub-categoría al cambiar sección
            continue

        # ── Col 0 numérico SIN precio: sub-categoría / título de grupo ──
        if is_numeric_code and desc and not tiene_precio:
            current_subcategory = desc
            continue

        # ── Col 0 numérico CON precio: producto real → construir nombre completo ──
        if is_numeric_code and tiene_precio:
            parts = []
            if current_section:
                parts.append(current_section.title())
            if current_subcategory:
                parts.append(current_subcategory.title())
            if desc:
                parts.append(desc)
            
            # Deduplicar palabras repetidas en la jerarquía (ej: COMPASES - COMPASES PLANTEC)
            dedup_parts = remove_duplicate_words_hierarchical(parts)
            nombre_completo = " - ".join(dedup_parts) if dedup_parts else desc

            new_vals = list(vals)
            if idx_desc is not None:
                new_vals[idx_desc] = nombre_completo
            all_rows.append(new_vals)

    if not all_rows:
        logger.warning(f"Sin filas de datos en {os.path.basename(filepath)}")
        return None

    df = pd.DataFrame(all_rows, columns=col_names)
    df.dropna(how="all", inplace=True)

    # Detectar columnas del DataFrame resultante
    cols       = df.columns.tolist()
    sku_col    = detect_column(cols, SKU_PATS)
    nombre_col = detect_column(cols, NOMBRE_PATS)
    precio_col = detect_column(cols, PRECIO_PATS)
    barra_col  = detect_column(cols, BARRA_PATS)

    logger.info(f"  Mapeado → SKU='{sku_col}' | Nombre='{nombre_col}' | Precio='{precio_col}' | Barras='{barra_col}'")

    result = pd.DataFrame()
    result["sku"]           = df[sku_col].astype(str).str.strip() if sku_col else None
    result["nombre"]        = df[nombre_col].astype(str).str.strip() if nombre_col else None
    result["precio"]        = df[precio_col].apply(clean_price) if precio_col else None
    result["codigo_barras"] = df[barra_col].apply(clean_barcode) if barra_col else None

    result = result[result["nombre"].notna() & ~result["nombre"].isin(["nan", "NaN", ""])]
    result = result[result["precio"].notna()]

    if result is not None and not result.empty:
        result["nombre"] = result["nombre"].apply(clean_origin)

    logger.info(f"  PLANTEC-multi: {len(result) if result is not None else 0} productos normalizados")
    return result


def process_powerland(filepath):
    """
    Lista Powerland — 3 columnas: Código | Descripción | Precio (sin código de barras).
    Detección automática de encabezado.
    """
    logger.info(f"Preprocesando {os.path.basename(filepath)}")

    df_raw = pd.read_excel(filepath, header=None)
    header_row = find_header_row(df_raw)
    if header_row is None:
        logger.warning(f"No se encontró encabezado en {os.path.basename(filepath)}")
        return None

    df = build_dataframe(df_raw, header_row)
    df.columns = [normalize_col_name(str(c)) for c in df.columns]
    df.dropna(how="all", inplace=True)

    col_list   = df.columns.tolist()
    sku_col    = detect_column(col_list, SKU_PATS) or col_list[0]
    nombre_col = detect_column(col_list, NOMBRE_PATS) or (col_list[1] if len(col_list) > 1 else None)
    precio_col = detect_column(col_list, PRECIO_PATS) or (col_list[2] if len(col_list) > 2 else None)

    logger.info(f"  Mapeado → SKU='{sku_col}' | Nombre='{nombre_col}' | Precio='{precio_col}' | Barras=None")

    result = pd.DataFrame()
    result["sku"]           = df[sku_col].astype(str).str.strip() if sku_col else None
    result["nombre"]        = df[nombre_col].astype(str).str.strip() if nombre_col else None
    result["precio"]        = df[precio_col].apply(clean_price) if precio_col else None
    result["codigo_barras"] = None

    # Filtrar: sku debe empezar con dígito (descarta títulos de sección)
    result = result[result["sku"].apply(lambda x: bool(re.match(r"^\d", str(x))))]
    result = result[result["precio"].notna()]
    result = result[result["nombre"].notna() & ~result["nombre"].isin(["nan", "NaN", ""])]
    result = result.reset_index(drop=True)

    logger.info(f"  POWERLAND: {len(result)} productos normalizados (sin código de barras)")
    return result


# ─────────────────────────────────────────────
# Función principal de preprocesamiento
# ─────────────────────────────────────────────

# Mapa de archivos → procesador correspondiente
FILES_CONFIG = [
    ("Lista Ale.xlsx",       process_ale),
    ("Lista Plantec 1.xlsx", process_plantec1),
    ("Lista Plantec 2.xlsx", process_plantec_multipage),
    ("Lista Plantec 3.xlsx", process_plantec_multipage),
    ("Lista Plantec 4.xlsx", process_plantec_multipage),
    ("Lista Plantec 5.xlsx", process_plantec_multipage),
    ("Lista Powerland.xlsx", process_powerland),
]


def preprocess_all(raw_dir: str, processed_dir: str) -> dict:
    """
    Recorre todos los archivos de proveedor configurados, los normaliza
    a 4 columnas estandarizadas y los guarda en processed_dir.

    Args:
        raw_dir:       Directorio con los Excel originales (data/raw)
        processed_dir: Directorio de salida para archivos normalizados (data/processed)

    Returns:
        Dict {filename: DataFrame} con los resultados procesados.
    """
    os.makedirs(processed_dir, exist_ok=True)
    logger.info("=" * 55)
    logger.info("PREPROCESAMIENTO: Normalizando listas de precios")
    logger.info("=" * 55)

    results = {}

    for filename, processor in FILES_CONFIG:
        filepath = os.path.join(raw_dir, filename)

        if not os.path.exists(filepath):
            logger.warning(f"Archivo no encontrado, se omite: {filename}")
            continue

        try:
            df = processor(filepath)

            if df is not None and not df.empty:
                out_name = filename.replace(".xlsx", "_normalizado.xlsx")
                out_path = os.path.join(processed_dir, out_name)
                df.to_excel(out_path, index=False)
                logger.info(f"  Guardado → {out_name} ({len(df)} filas)")
                results[filename] = df
            else:
                logger.warning(f"  Sin datos para {filename}")

        except Exception as e:
            logger.error(f"Error preprocesando {filename}: {e}", exc_info=True)

    total = sum(len(df) for df in results.values())
    logger.info("=" * 55)
    logger.info(f"Preprocesamiento completo: {len(results)}/{len(FILES_CONFIG)} archivos | {total} productos totales")
    logger.info("=" * 55)

    return results

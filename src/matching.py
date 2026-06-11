import re
from datetime import datetime
from sqlalchemy.orm import Session
from rapidfuzz import fuzz
from src.utils.logger import setup_logger
from src.utils.helpers import load_config
from src.models import (
    get_db_session, CatalogoMaestro, ProductoProveedor, 
    CoincidenciaPendiente, AuditoriaUnificacion
)

logger = setup_logger()

# Diccionario de abreviaturas y equivalencias comunes para librerías en Argentina
ABBREVIATIONS = {
    r'\blap\b': 'lapicera',
    r'\bboli\b': 'boligrafo',
    r'\bbolig\b': 'boligrafo',
    r'\bpint\b': 'pintura',
    r'\bmicrofib\b': 'microfibra',
    r'\brep\b': 'repuesto',
    r'\baz\b': 'azul',
    r'\bng\b': 'negro',
    r'\broj\b': 'rojo',
    r'\bvd\b': 'verde',
    r'\bbl\b': 'blanco',
    r'\bcomp\b': 'completo',
    r'\bun\b': 'unidades',
    r'\bpaq\b': 'paquete',
    r'\bcaj\b': 'caja',
    r'\bbroch\b': 'broches',
    r'\babroch\b': 'abrochadora',
    r'\bestil\b': 'estilografo',
    r'\bmarc\b': 'marcador',
    r'\bresalt\b': 'resaltador',
    r'\bsacap\b': 'sacapuntas',
    r'\bcuad\b': 'cuaderno',
    r'\bcarp\b': 'carpeta',
    r'\btij\b': 'tijera',
}

def clean_and_normalize_name(name: str) -> str:
    """
    Normaliza el nombre del producto: minúsculas, remoción de acentos,
    remoción de puntuación y traducción de abreviaturas comunes.
    """
    if not name:
        return ""
    
    # 1. Convertir a minúsculas
    s = name.lower().strip()
    
    # 2. Reemplazar acentos españoles
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ü': 'u', 'ñ': 'n'
    }
    for orig, rep in replacements.items():
        s = s.replace(orig, rep)
        
    # 3. Remover caracteres de puntuación decorativos
    s = re.sub(r'[.\-_,;:/()#]', ' ', s)
    
    # 4. Traducir abreviaturas
    for pattern, replacement in ABBREVIATIONS.items():
        s = re.sub(pattern, replacement, s)
        
    # 5. Colapsar espacios múltiples
    s = re.sub(r'\s+', ' ', s).strip()
    return s.upper()

def expand_abbreviations_in_name(name: str) -> str:
    """
    Expande las abreviaturas comunes en un nombre para hacerlo completamente legible en el catálogo.
    Conserva la estructura original del nombre pero reemplaza abreviaturas como 'MARC.' por 'MARCADOR'.
    """
    if not name:
        return ""
    
    # Reemplazar puntos que no sean decimales (no rodeados de dígitos a ambos lados) por espacio
    processed_name = re.sub(r'(?<!\d)\.|\.(?!\d)', ' ', name)
    
    # 1. Separar palabras
    words = processed_name.split()
    expanded_words = []
    
    for w in words:
        # Remover puntuación al inicio/final para buscar en el diccionario (ej: "marc" -> "marc")
        clean_w = re.sub(r'^[.\-_,;:/()#]+|[.\-_,;:/()#]+$', '', w).lower()
        
        expanded = clean_w
        # Buscar en el diccionario de abreviaturas
        for pattern, replacement in ABBREVIATIONS.items():
            # Quitar los límites de palabra \b del patrón de búsqueda para coincidir exactamente
            clean_pattern = pattern.replace(r'\b', '')
            if clean_w == clean_pattern:
                expanded = replacement
                break
                
        # Si fue expandida, la agregamos en mayúsculas. Si no, conservamos la palabra original
        if expanded != clean_w:
            expanded_words.append(expanded.upper())
        else:
            expanded_words.append(w)
            
    return " ".join(expanded_words)

def clean_existing_abbreviations(db_path: str = None) -> int:
    """
    Recorre el catálogo maestro y expande las abreviaturas existentes en nombre_normalizado.
    Retorna la cantidad de productos actualizados.
    """
    logger.info("Iniciando limpieza de abreviaturas en el catálogo maestro existente...")
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    updated_count = 0
    try:
        products = session.query(CatalogoMaestro).all()
        for p in products:
            expanded = expand_abbreviations_in_name(p.nombre_normalizado)
            if expanded != p.nombre_normalizado:
                logger.info(f"Limpiando nombre de SKU {p.master_sku}: '{p.nombre_normalizado}' -> '{expanded}'")
                p.nombre_normalizado = expanded
                updated_count += 1
        if updated_count > 0:
            session.commit()
            logger.info(f"Limpieza finalizada. Se actualizaron {updated_count} productos.")
        else:
            logger.info("Limpieza finalizada. No se encontraron abreviaturas para corregir.")
        return updated_count
    except Exception as e:
        session.rollback()
        logger.error(f"Error limpiando abreviaturas en catálogo maestro: {e}", exc_info=True)
        raise
    finally:
        session.close()

# Lista de marcas conocidas por defecto
DEFAULT_KNOWN_BRANDS = [
    "BIC", "ROTRING", "DELI", "KANGARO", "FILGO", "PLANTEC", "POWERLAND", 
    "PIZZINI", "FABER-CASTELL", "FABER CASTELL", "SIMBALL", "EBR", "ALBA", 
    "EZCO", "MOOVING", "STABILO", "MAPED", "ALBORADA", "DOMS", "EDDING", "EZ",
    "EPICA"
]

# Sinónimos para normalizar marcas
BRAND_SYNONYMS = {
    "FABER CASTELL": "FABER-CASTELL",
    "FABER": "FABER-CASTELL",
    "ROTR": "ROTRING",
    "PLANT": "PLANTEC",
    "POWER": "POWERLAND",
    "EZ": "EZCO",
}

# Términos comunes de librería que NO son marcas (blacklist)
BRAND_BLACKLIST = {
    "LAPICERA", "BOLIGRAFO", "PINTURA", "MICROFIBRA", "REPUESTO",
    "AZUL", "NEGRO", "ROJO", "VERDE", "BLANCO", "COMPLETO",
    "UNIDADES", "PAQUETE", "CAJA", "BROCHES", "ABROCHADORA",
    "ESTILOGRAFO", "MARCADOR", "RESALTADOR", "SACAPUNTAS",
    "CUADERNO", "CARPETA", "TIJERA", "GOMA", "ADHESIVO",
    "REGLA", "CINTA", "PAPEL", "LAPIS", "LAPIZ", "ROLLER",
    "PORTAMINAS", "MINAS", "PUNTA", "PINCEL", "PLASTICO",
    "METALICO", "COLOR", "COLORES", "VALIJA", "BLISTER",
    "JUMBO", "BRUSH", "ACRILICO", "TEMPERA", "FOLIO",
    "BIBLIORATO", "SACABOCADO", "PIZARRA", "EXHIBIDOR",
    "LIBRO", "MOVIL", "BARCO", "CURSIVAS", "DIBUJO",
    "ABECEDARIO", "ABACO", "ADAPTADOR", "ACUARELA", "ALFILER",
    "ALMOHADILLA", "ARGENTINA", "ARO", "ARTE", "ATRIL", "AVION",
    "BANDA", "BANDEJA", "BANDERA", "BARNIZ", "BARRA", "BASE",
    "BASTIDOR", "BETUN", "BLOCK", "BOBINA", "BOLETO", "BOLSA",
    "BOLSILLO", "BORRADOR", "BORRATINTA", "BOTELLA", "BRILLANTINA",
    "BROCHE", "CALCULADORA", "CALENDARIO", "CANOPLA", "CARBONICO",
    "CARBONILLA", "CARGADOR", "CARTON", "CARTUCHO", "CARTULINA",
    "CHINCHE", "CIZALLA", "CLIP", "COLA", "CORCHO", "CORRECTOR",
    "CORTANTE", "CRAYON", "CREPE", "CUCHILLA", "DADO", "DICCIONARIO",
    "DILUYENTE", "DISPLAY", "ENGRAMPADORA", "ESCALAS", "ESCUADRA",
    "ESFERA", "ESFUMINOS", "ESTUCHE", "FIBRA", "FICHA", "FICHERO",
    "GEL", "GLOBO", "GRAFITO", "HILO", "HOJA", "IMAN", "INDICE",
    "JUEGO", "KIT", "LACA", "LAMINA", "LOMO", "LUPA", "LUZ",
    "MADERA", "MALETIN", "MAQUINA", "MASA", "MASILLA", "MASTIL",
    "MINA", "MOCHILA", "ORGANIZADOR", "PALITO", "PEGAMENTO",
    "PERFORADORA", "PERGAMINO", "PINCELES", "PINCELETA", "PINS",
    "PINZA", "PISTOLA", "PLANCHA", "PLANILLA", "PLASTILINA",
    "PORTARROLLO", "POTE", "PURPURINA", "RECIBO", "REDONDEADORA",
    "REGLAS", "RELOJ", "RESMA", "SOBRE", "TABLA", "TABLERO",
    "TACO", "TALONARIO", "TANQUE", "TANZA", "TAPA", "TARJETA",
    "TAZA", "TELA", "TELGOPOR", "TERMO", "TINTA", "TIZA",
    "TUBO", "VALE", "VARILLA", "VASO", "VIDRIO", "YESO", "IDEM",
    "DIAMETRO", "ELASTIA", "ELASTICA", "ELASTICO"
}

def extract_significant_numbers(name: str) -> set:
    """
    Extrae números significativos de un nombre de producto (cantidades, tamaños, modelos).
    Se usa para detectar variantes que NO deben unificarse.
    Ej: 'X 24 COLORES' → {'24'}, 'DE 12 CM' → {'12'}
    """
    numbers = re.findall(r'\b\d+(?:[.,]\d+)?\b', name)
    result = set()
    for n in numbers:
        n_norm = n.replace(',', '.')
        try:
            val = float(n_norm)
            result.add(str(int(val)) if val == int(val) else str(val))
        except (ValueError, OverflowError):
            pass
    return result

def names_have_compatible_numbers(name1: str, name2: str) -> bool:
    """
    Retorna True si los valores numéricos en dos nombres de producto son compatibles.
    Dos nombres son INCOMPATIBLES si ambos contienen números y los conjuntos son disjuntos.
    Ej: 'X 12 COLORES' vs 'X 24 COLORES' → {12} ∩ {24} = ∅ → INCOMPATIBLE
    Ej: 'N°10 CAJA X 12' vs 'N°10 BLISTER' → {10,12} ∩ {10} ≠ ∅ → COMPATIBLE
    Si uno o ambos no tienen números → COMPATIBLE (no hay conflicto numérico)
    """
    nums1 = extract_significant_numbers(name1)
    nums2 = extract_significant_numbers(name2)
    if nums1 and nums2 and nums1.isdisjoint(nums2):
        return False
    return True

def extract_brand(name: str, db_session: Session = None) -> str:
    """
    Extrae la marca basándose en nombres de marcas conocidos.
    1. Si encuentra alguna marca conocida en el título, la retorna (normalizada con sinónimos).
    2. Si no, aplica el fallback de la primera palabra del título que tenga al menos 3 letras
       y no esté en la lista negra (blacklist).
    """
    if not name:
        return "VARIOS"
        
    name_normalized = clean_and_normalize_name(name)
    
    # 1. Obtener lista de marcas conocidas (dinámica + estática)
    known = set(DEFAULT_KNOWN_BRANDS)
    if db_session:
        try:
            # Obtener marcas reales ya ingresadas en el catálogo maestro
            db_brands = [
                b[0].strip().upper() 
                for b in db_session.query(CatalogoMaestro.marca).distinct().all() 
                if b[0] and b[0].strip().upper() not in ["VARIOS", ""]
            ]
            known.update(db_brands)
        except Exception as e:
            logger.warning(f"No se pudieron cargar marcas de la DB: {e}")
            
    # 2. Buscar si alguna marca conocida está contenida en el nombre normalizado
    words = name_normalized.split()
    
    # Ordenar marcas conocidas por longitud descendente para que "FABER CASTELL" tenga prioridad sobre "FABER"
    sorted_known = sorted(list(known), key=len, reverse=True)
    for brand in sorted_known:
        brand_norm = clean_and_normalize_name(brand)
        # Buscar la marca normalizada como frase completa o subcadena exacta con límites de palabra
        pattern = r'\b' + re.escape(brand_norm) + r'\b'
        if re.search(pattern, name_normalized):
            mapped_brand = BRAND_SYNONYMS.get(brand_norm, brand_norm)
            return mapped_brand
            
    # 3. Fallback: tomar la primera palabra del nombre que tenga al menos 3 letras y no esté en blacklist
    for w in words:
        if len(w) >= 3 and w not in BRAND_BLACKLIST:
            return BRAND_SYNONYMS.get(w, w)
            
    return "VARIOS"

def generate_master_sku(brand: str, category: str, name: str, db_session: Session) -> str:
    """
    Genera un SKU Maestro estructurado y único: [CAT]-[BRAND]-[PRODUCT_LINE]-[VAR]
    """
    brand_prefix = brand[:4].replace(" ", "").upper()
    cat_prefix = category[:3].replace(" ", "").upper()
    
    # Limpiar nombre para sacar la marca y palabras comunes
    clean_title = clean_and_normalize_name(name).replace(brand.lower(), "")
    words = [w[:4] for w in clean_title.split() if len(w) >= 3]
    
    # Tomar las primeras dos palabras para la línea de producto y variación
    prod_line = words[0].upper() if len(words) > 0 else "PROD"
    variant = words[1].upper() if len(words) > 1 else "VAR"
    
    base_sku = f"{cat_prefix}-{brand_prefix}-{prod_line}-{variant}"
    
    # Garantizar unicidad agregando un sufijo numérico si ya existe
    counter = 1
    final_sku = base_sku
    while db_session.query(CatalogoMaestro).filter(CatalogoMaestro.master_sku == final_sku).first():
        final_sku = f"{base_sku}-{counter}"
        counter += 1
        
    return final_sku

def run_matching_engine(db_path: str = None) -> dict:
    """
    Ejecuta el motor de deduplicación semántica y unificación.
    1. Match determinista por código de barras (EAN).
    2. Similitud fuzzy de texto sobre nombres normalizados.
    3. Clasificación:
       - Similitud > 90% + Barcode: Auto-Merge.
       - Similitud >= 60%: Sugerencia insertada en coincidencias_pendientes (Validación Humana).
       - Similitud < 60%: Se clasifica como Producto Nuevo.
    """
    logger.info("Ejecutando motor de unificación semántica y deduplicación...")
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    
    exact_ean_count = 0
    pending_match_count = 0
    new_product_count = 0
    
    try:
        # Cargar catálogo maestro y productos de proveedores pendientes
        master_catalog = session.query(CatalogoMaestro).all()
        pending_provider_products = session.query(ProductoProveedor).filter(
            ProductoProveedor.master_sku == None,
            ProductoProveedor.estado_unificacion == 'PENDIENTE'
        ).all()
        
        logger.info(f"Productos en catálogo maestro: {len(master_catalog)}")
        logger.info(f"Productos de proveedores sin unificar: {len(pending_provider_products)}")
        
        # Mapeo rápido para EAN
        master_by_ean = {m.codigo_barras: m for m in master_catalog if m.codigo_barras}
        
        # Obtener mapeo de master_sku -> set(proveedor_id) de productos ya vinculados
        linked_providers_by_sku = {}
        for pp in session.query(ProductoProveedor).filter(ProductoProveedor.master_sku != None).all():
            if pp.master_sku not in linked_providers_by_sku:
                linked_providers_by_sku[pp.master_sku] = set()
            linked_providers_by_sku[pp.master_sku].add(pp.proveedor_id)
            
        # Pre-calcular nombres normalizados del catálogo maestro para evitar llamar a clean_and_normalize_name millones de veces
        master_normalized = [
            (m_prod, clean_and_normalize_name(m_prod.nombre_normalizado))
            for m_prod in master_catalog
        ]
        
        for p_prov in pending_provider_products:
            # 1. Match Exacto por Código de Barras (EAN)
            if p_prov.codigo_barras and p_prov.codigo_barras in master_by_ean:
                m_prod = master_by_ean[p_prov.codigo_barras]
                linked_provs = linked_providers_by_sku.get(m_prod.master_sku, set())
                if p_prov.proveedor_id not in linked_provs:
                    p_prov.master_sku = m_prod.master_sku
                    p_prov.estado_unificacion = 'APROBADO'
                    
                    # Actualizar costo si es mayor para protección de márgenes
                    if p_prov.costo_calculado > m_prod.precio_costo:
                        m_prod.precio_costo = p_prov.costo_calculado
                        m_prod.precio_venta = round(m_prod.precio_costo * (1 + m_prod.margen_ganancia), 2)
                    
                    # Auditar decisión
                    audit = AuditoriaUnificacion(
                        producto_proveedor_id=p_prov.id,
                        master_sku=m_prod.master_sku,
                        accion='AUTO_MERGE',
                        score_similitud=100.0,
                        detalles=f"Coincidencia exacta de código de barras: {p_prov.codigo_barras}"
                    )
                    session.add(audit)
                    
                    # Actualizar memoria de proveedores vinculados
                    if m_prod.master_sku not in linked_providers_by_sku:
                        linked_providers_by_sku[m_prod.master_sku] = set()
                    linked_providers_by_sku[m_prod.master_sku].add(p_prov.proveedor_id)
                    
                    exact_ean_count += 1
                    continue
            
            # 2. Match Difuso por Similitud de Texto
            norm_prov_name = clean_and_normalize_name(p_prov.nombre_original)
            best_score = 0.0
            best_m_prod = None
            
            for m_prod, norm_master_name in master_normalized:
                # Evitar comparar con productos maestros que ya tengan vinculado este proveedor
                linked_provs = linked_providers_by_sku.get(m_prod.master_sku, set())
                if p_prov.proveedor_id in linked_provs:
                    continue
                    
                # Comparar usando token_sort_ratio
                score = fuzz.token_sort_ratio(norm_prov_name, norm_master_name)
                
                # Penalizar fuertemente si los valores numéricos en los nombres son incompatibles.
                # Evita unificar: 'X 12 COLORES' con 'X 24 COLORES', '2 CM' con '12 CM', etc.
                if not names_have_compatible_numbers(norm_prov_name, norm_master_name):
                    score = score * 0.5
                
                if score > best_score:
                    best_score = score
                    best_m_prod = m_prod
            
            # Clasificar coincidencia según el score de similitud (Umbral aumentado a 80.0%)
            if best_m_prod and best_score >= 80.0:
                # Insertar en coincidencias pendientes para validación manual
                # Validar que no exista ya la sugerencia pendiente activa
                existing = session.query(CoincidenciaPendiente).filter(
                    CoincidenciaPendiente.producto_proveedor_id == p_prov.id,
                    CoincidenciaPendiente.master_sku_sugerido == best_m_prod.master_sku,
                    CoincidenciaPendiente.estado == 'PENDIENTE'
                ).first()
                
                if not existing:
                    new_pending = CoincidenciaPendiente(
                        producto_proveedor_id=p_prov.id,
                        master_sku_sugerido=best_m_prod.master_sku,
                        similitud=round(best_score, 1),
                        estado='PENDIENTE'
                    )
                    session.add(new_pending)
                    pending_match_count += 1
            else:
                # Similitud menor al 80%: Crear como producto nuevo en el catálogo
                brand = extract_brand(p_prov.nombre_original, session)
                category = "VARIOS"
                new_sku = generate_master_sku(brand, category, p_prov.nombre_original, session)
                
                # Usar expand_abbreviations_in_name para limpiar el nombre del catálogo maestro
                clean_name = expand_abbreviations_in_name(p_prov.nombre_original)
                
                new_master = CatalogoMaestro(
                    master_sku=new_sku,
                    codigo_barras=p_prov.codigo_barras,
                    nombre_normalizado=clean_name,
                    marca=brand,
                    categoria=category,
                    precio_costo=p_prov.costo_calculado,
                    margen_ganancia=0.60,
                    precio_venta=round(p_prov.costo_calculado * 1.60, 2)
                )
                session.add(new_master)
                session.flush()  # Asegurar que el SKU esté disponible en la DB
                
                # Vincular producto de proveedor
                p_prov.master_sku = new_sku
                p_prov.estado_unificacion = 'APROBADO'
                
                # Auditar creación
                audit = AuditoriaUnificacion(
                    producto_proveedor_id=p_prov.id,
                    master_sku=new_sku,
                    accion='AUTO_MERGE',
                    score_similitud=100.0,
                    detalles=f"Producto nuevo sin coincidencias (máxima similitud: {best_score:.1f}%). Creado SKU Maestro: {new_sku}"
                )
                session.add(audit)
                new_product_count += 1
                
                # Actualizar memoria para evitar duplicar este mismo producto nuevo en esta corrida
                master_catalog.append(new_master)
                master_normalized.append((new_master, clean_and_normalize_name(clean_name)))
                if new_master.codigo_barras:
                    master_by_ean[new_master.codigo_barras] = new_master
                    
                # Registrar proveedor vinculado
                linked_providers_by_sku[new_sku] = {p_prov.proveedor_id}
                    
        session.commit()
        logger.info(f"Unificación completada. EAN Automáticos: {exact_ean_count}, Pendientes revisión: {pending_match_count}, Nuevos Creados: {new_product_count}")
        return {
            "ean_automatch": exact_ean_count,
            "pending_manual_review": pending_match_count,
            "new_products_created": new_product_count
        }
    except Exception as e:
        session.rollback()
        logger.error(f"Error en motor de unificación: {e}", exc_info=True)
        raise
    finally:
        session.close()

def approve_pending_match(pending_id: int, db_path: str = None, operator_id: str = "ADMIN", overrides: dict = None) -> bool:
    """
    Aprobación manual de una coincidencia de unificación sugerida por el motor, permitiendo modificaciones personalizadas.
    """
    logger.info(f"Aprobando manualmente coincidencia pendiente ID: {pending_id}")
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    
    try:
        pending = session.query(CoincidenciaPendiente).filter(
            CoincidenciaPendiente.id == pending_id,
            CoincidenciaPendiente.estado == 'PENDIENTE'
        ).first()
        
        if not pending:
            logger.warning(f"No se encontró la coincidencia pendiente activa con ID {pending_id}")
            return False
            
        p_prov = session.query(ProductoProveedor).filter(ProductoProveedor.id == pending.producto_proveedor_id).first()
        m_prod = session.query(CatalogoMaestro).filter(CatalogoMaestro.master_sku == pending.master_sku_sugerido).first()
        
        # 1. Unificar vinculando master_sku
        p_prov.master_sku = m_prod.master_sku
        p_prov.estado_unificacion = 'APROBADO'
        
        # 2. Aplicar overrides manuales si existen
        if overrides:
            if 'nombre_normalizado' in overrides and overrides['nombre_normalizado']:
                m_prod.nombre_normalizado = overrides['nombre_normalizado'].strip().upper()
            if 'marca' in overrides and overrides['marca']:
                m_prod.marca = overrides['marca'].strip().upper()
            if 'categoria' in overrides and overrides['categoria']:
                m_prod.categoria = overrides['categoria'].strip().upper()
            if 'precio_costo' in overrides and overrides['precio_costo'] is not None:
                m_prod.precio_costo = float(overrides['precio_costo'])
            if 'margen_ganancia' in overrides and overrides['margen_ganancia'] is not None:
                m_prod.margen_ganancia = float(overrides['margen_ganancia'])
            if 'codigo_barras' in overrides:
                m_prod.codigo_barras = overrides['codigo_barras'].strip() if overrides['codigo_barras'] else None
            
            # Recalcular precio de venta final
            m_prod.precio_venta = round(m_prod.precio_costo * (1 + m_prod.margen_ganancia), 2)
        else:
            # 3. Lógica por defecto (tomar costo máximo de los proveedores)
            if p_prov.costo_calculado > m_prod.precio_costo:
                m_prod.precio_costo = p_prov.costo_calculado
                m_prod.precio_venta = round(m_prod.precio_costo * (1 + m_prod.margen_ganancia), 2)
                
            # Guardar código de barras si el catálogo no lo tenía y el proveedor sí
            if not m_prod.codigo_barras and p_prov.codigo_barras:
                m_prod.codigo_barras = p_prov.codigo_barras
            
        # 4. Actualizar estado de la coincidencia
        pending.estado = 'APROBADO'
        
        # 5. Rechazar el resto de coincidencias sugeridas alternativas para este mismo producto proveedor
        session.query(CoincidenciaPendiente).filter(
            CoincidenciaPendiente.producto_proveedor_id == p_prov.id,
            CoincidenciaPendiente.id != pending_id
        ).update({"estado": "RECHAZADO"})
        
        # 6. Registrar en auditoría
        audit = AuditoriaUnificacion(
            producto_proveedor_id=p_prov.id,
            master_sku=m_prod.master_sku,
            accion='MANUAL_MERGE',
            score_similitud=pending.similitud,
            detalles=f"PR unificado por operador: {operator_id}. Edición manual: {overrides is not None}"
        )
        session.add(audit)
        
        session.commit()
        logger.info(f"Unificación exitosa: '{p_prov.nombre_original}' unificado con '{m_prod.nombre_normalizado}' ({m_prod.master_sku})")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error al aprobar coincidencia {pending_id}: {e}", exc_info=True)
        raise
    finally:
        session.close()

def reject_pending_match(pending_id: int, db_path: str = None) -> bool:
    """
    Rechaza una coincidencia sugerida por el motor. El producto proveedor queda sin unificar.
    """
    logger.info(f"Rechazando sugerencia de coincidencia ID: {pending_id}")
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    
    try:
        pending = session.query(CoincidenciaPendiente).filter(
            CoincidenciaPendiente.id == pending_id,
            CoincidenciaPendiente.estado == 'PENDIENTE'
        ).first()
        
        if not pending:
            logger.warning(f"No se encontró la coincidencia pendiente activa con ID {pending_id}")
            return False
            
        pending.estado = 'RECHAZADO'
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error al rechazar sugerencia {pending_id}: {e}", exc_info=True)
        raise
    finally:
        session.close()

def split_and_create_new(prod_provider_id: int, db_path: str = None) -> str:
    """
    Desvincula un producto de proveedor de su SKU actual y lo crea como un nuevo producto maestro.
    Útil para deshacer unificaciones incorrectas (Rollback / Split).
    """
    logger.info(f"Creando producto proveedor ID {prod_provider_id} como nuevo producto maestro independiente...")
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    
    try:
        p_prov = session.query(ProductoProveedor).filter(ProductoProveedor.id == prod_provider_id).first()
        if not p_prov:
            logger.warning(f"No se encontró producto proveedor con ID {prod_provider_id}")
            return ""
            
        old_sku = p_prov.master_sku
        
        # Generar nuevo master
        brand = extract_brand(p_prov.nombre_original, session)
        category = "VARIOS"
        new_sku = generate_master_sku(brand, category, p_prov.nombre_original, session)
        
        new_master = CatalogoMaestro(
            master_sku=new_sku,
            codigo_barras=p_prov.codigo_barras,
            nombre_normalizado=expand_abbreviations_in_name(p_prov.nombre_original),
            marca=brand,
            categoria=category,
            precio_costo=p_prov.costo_calculado,
            margen_ganancia=0.60,
            precio_venta=round(p_prov.costo_calculado * 1.60, 2)
        )
        session.add(new_master)
        session.flush()
        
        p_prov.master_sku = new_sku
        p_prov.estado_unificacion = 'APROBADO'
        
        # Registrar auditoría de desvinculación
        audit = AuditoriaUnificacion(
            producto_proveedor_id=p_prov.id,
            master_sku=new_sku,
            accion='SPLIT',
            score_similitud=0.0,
            detalles=f"Desvinculado del SKU Maestro anterior '{old_sku}' y creado como nuevo SKU independiente '{new_sku}'"
        )
        session.add(audit)
        
        session.commit()
        logger.info(f"Split completado. Producto re-asignado al nuevo SKU: {new_sku}")
        return new_sku
    except Exception as e:
        session.rollback()
        logger.error(f"Error realizando split para producto {prod_provider_id}: {e}", exc_info=True)
        raise
    finally:
        session.close()

def fix_wrong_numeric_merges(db_path: str = None) -> int:
    """
    Detecta y corrige unificaciones incorrectas causadas por el matching fuzzy
    que no respetó diferencias numéricas en los nombres de productos.
    
    Ejemplo de error corregido: 'ESFERA TELGOPOR 2 CM' y 'ESFERA TELGOPOR 12 CM'
    unificadas bajo el mismo master_sku, resultando en el costo de 12cm asignado
    al producto de 2cm (o viceversa).
    
    La función:
    1. Busca master_skus con múltiples productos vinculados (APROBADO)
    2. Para cada grupo, identifica el producto cuyo nombre es más similar al del catálogo maestro
    3. Los demás productos con valores numéricos incompatibles se desvinculan y vuelven a PENDIENTE
    4. En el próximo run del motor de matching (con la penalización numérica activa), serán
       reclasificados correctamente como nuevos productos separados.
    
    Retorna la cantidad de desvinculaciones realizadas.
    """
    logger.info("Iniciando corrección de unificaciones incorrectas por diferencias numéricas...")
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    split_count = 0
    
    try:
        from sqlalchemy import func
        
        # 1. Encontrar master_skus con múltiples productos de proveedor APROBADOS
        multi_linked_skus = session.query(
            ProductoProveedor.master_sku
        ).filter(
            ProductoProveedor.estado_unificacion == 'APROBADO',
            ProductoProveedor.master_sku.isnot(None)
        ).group_by(ProductoProveedor.master_sku).having(func.count() > 1).all()
        
        logger.info(f"Master SKUs con múltiples productos vinculados: {len(multi_linked_skus)}")
        
        for (master_sku,) in multi_linked_skus:
            # Obtener el producto maestro
            master = session.query(CatalogoMaestro).filter(
                CatalogoMaestro.master_sku == master_sku
            ).first()
            if not master:
                continue
            
            # Obtener todos los productos de proveedor vinculados
            linked = session.query(ProductoProveedor).filter(
                ProductoProveedor.master_sku == master_sku,
                ProductoProveedor.estado_unificacion == 'APROBADO'
            ).all()
            
            if len(linked) < 2:
                continue
            
            master_norm = clean_and_normalize_name(master.nombre_normalizado)
            
            # Identificar el "mejor" producto: el más similar al nombre maestro
            best_product = max(
                linked,
                key=lambda p: fuzz.token_sort_ratio(clean_and_normalize_name(p.nombre_original), master_norm)
            )
            
            # Revisar el resto: si alguno tiene números incompatibles con el maestro → desvincular
            for p_prov in linked:
                if p_prov.id == best_product.id:
                    continue
                
                p_norm = clean_and_normalize_name(p_prov.nombre_original)
                
                if not names_have_compatible_numbers(p_norm, master_norm):
                    logger.info(
                        f"[FIX] Desvinculando '{p_prov.nombre_original}' (SKU prov: {p_prov.sku_proveedor}) "
                        f"del master '{master.nombre_normalizado}' ({master_sku}). "
                        f"Números '{extract_significant_numbers(p_norm)}' incompatibles con '{extract_significant_numbers(master_norm)}'"
                    )
                    # Marcar pendiente de coincidencias previas como RECHAZADAS
                    session.query(CoincidenciaPendiente).filter(
                        CoincidenciaPendiente.producto_proveedor_id == p_prov.id
                    ).update({"estado": "RECHAZADO"})
                    
                    # Desvincular del master
                    p_prov.master_sku = None
                    p_prov.estado_unificacion = 'PENDIENTE'
                    split_count += 1
        
        session.commit()
        
        if split_count > 0:
            logger.info(f"Corrección completada. Se desvincularon {split_count} productos con números incompatibles.")
        else:
            logger.info("Corrección completada. No se encontraron unificaciones incorrectas por números.")
        
        return split_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error durante la corrección de unificaciones numéricas: {e}", exc_info=True)
        raise
    finally:
        session.close()


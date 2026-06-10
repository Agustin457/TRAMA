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

def extract_brand(name: str) -> str:
    """
    Extrae dinámicamente la marca basándose en palabras conocidas.
    Si no encuentra ninguna, asume la primera palabra significativa.
    """
    name_normalized = clean_and_normalize_name(name)
    known_brands = ["BIC", "ROTRING", "DELI", "KANGARO", "FILGO", "PLANTEC", "POWERLAND", "PIZZINI", "FABER CASTELL", "SIMBALL"]
    
    for brand in known_brands:
        if brand in name_normalized:
            return brand
            
    # Fallback: tomar la primera palabra del nombre si tiene al menos 3 letras
    words = [w for w in name_normalized.split() if len(w) >= 3]
    if words:
        return words[0]
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
        
        for p_prov in pending_provider_products:
            # 1. Match Exacto por Código de Barras (EAN)
            if p_prov.codigo_barras and p_prov.codigo_barras in master_by_ean:
                m_prod = master_by_ean[p_prov.codigo_barras]
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
                exact_ean_count += 1
                continue
            
            # 2. Match Difuso por Similitud de Texto
            norm_prov_name = clean_and_normalize_name(p_prov.nombre_original)
            best_score = 0.0
            best_m_prod = None
            
            for m_prod in master_catalog:
                norm_master_name = clean_and_normalize_name(m_prod.nombre_normalizado)
                # Comparar usando token_sort_ratio
                score = fuzz.token_sort_ratio(norm_prov_name, norm_master_name)
                
                if score > best_score:
                    best_score = score
                    best_m_prod = m_prod
            
            # Clasificar coincidencia según el score de similitud
            if best_m_prod and best_score >= 60.0:
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
                # Similitud menor al 60%: Crear como producto nuevo en el catálogo
                brand = extract_brand(p_prov.nombre_original)
                category = "VARIOS"
                new_sku = generate_master_sku(brand, category, p_prov.nombre_original, session)
                
                new_master = CatalogoMaestro(
                    master_sku=new_sku,
                    codigo_barras=p_prov.codigo_barras,
                    nombre_normalizado=p_prov.nombre_original,
                    marca=brand,
                    categoria=category,
                    precio_costo=p_prov.costo_calculado,
                    margen_ganancia=0.40,
                    precio_venta=round(p_prov.costo_calculado * 1.40, 2)
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
                if new_master.codigo_barras:
                    master_by_ean[new_master.codigo_barras] = new_master
                    
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
        brand = extract_brand(p_prov.nombre_original)
        category = "VARIOS"
        new_sku = generate_master_sku(brand, category, p_prov.nombre_original, session)
        
        new_master = CatalogoMaestro(
            master_sku=new_sku,
            codigo_barras=p_prov.codigo_barras,
            nombre_normalizado=p_prov.nombre_original,
            marca=brand,
            categoria=category,
            precio_costo=p_prov.costo_calculado,
            margen_ganancia=0.40,
            precio_venta=round(p_prov.costo_calculado * 1.40, 2)
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

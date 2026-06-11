import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.utils.helpers import load_config
from src.models import get_db_session, CatalogoMaestro, CoincidenciaPendiente, ProductoProveedor
from src.matching import approve_pending_match, reject_pending_match, split_and_create_new, extract_brand

app = FastAPI(
    title="Depósito Scanner & Matching App",
    description="Fase 4: App de Escaneo y Panel de Matching en un solo clic",
    version="1.0.0"
)

# Modelos Pydantic para validación de entrada
class ProductoCreate(BaseModel):
    master_sku: str = Field(..., min_length=1, description="SKU Maestro estructurado")
    nombre_normalizado: str = Field(..., min_length=1, description="Nombre normalizado del artículo")
    marca: str = Field(..., min_length=1, description="Marca del artículo")
    categoria: str = Field("VARIOS", description="Categoría del artículo")
    codigo_barras: Optional[str] = Field(None, description="Código de barras EAN")
    precio_costo: float = Field(0.0, ge=0.0, description="Precio de costo")
    margen_ganancia: float = Field(0.60, ge=0.0, description="Margen de ganancia (ej. 0.60)")

class ResolverMatch(BaseModel):
    action: str = Field(..., pattern="^(APROBAR|RECHAZAR)$", description="Acción: APROBAR o RECHAZAR")
    nombre_normalizado: Optional[str] = None
    marca: Optional[str] = None
    categoria: Optional[str] = None
    precio_costo: Optional[float] = None
    margen_ganancia: Optional[float] = None
    codigo_barras: Optional[str] = None

def get_db_path_local() -> str:
    try:
        config = load_config("config.yaml")
        return config.get("paths", {}).get("db_path", "data/etl_database.db")
    except Exception:
        return "data/etl_database.db"

@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    """
    Sirve el frontend HTML ligero responsivo optimizado para móviles.
    """
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if not os.path.exists(template_path):
        raise HTTPException(
            status_code=404, 
            detail="Plantilla index.html no encontrada. Por favor crea src/templates/index.html primero."
        )
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/producto/{barcode}")
def get_product_by_barcode(barcode: str):
    """
    Busca un producto en el catálogo por su código de barras.
    """
    db_path = get_db_path_local()
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    try:
        product = session.query(CatalogoMaestro).filter(CatalogoMaestro.codigo_barras == barcode.strip()).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto con código de barras '{barcode}' no encontrado en el catálogo maestro."
            )
        return {
            "master_sku": product.master_sku,
            "codigo_barras": product.codigo_barras,
            "nombre_normalizado": product.nombre_normalizado,
            "marca": product.marca,
            "categoria": product.categoria,
            "precio_costo": product.precio_costo,
            "margen_ganancia": product.margen_ganancia,
            "precio_venta": product.precio_venta,
            "id_woocommerce": product.id_woocommerce
        }
    finally:
        session.close()

@app.post("/api/producto", status_code=status.HTTP_201_CREATED)
def create_product(product_in: ProductoCreate):
    """
    Registra un nuevo producto en el catálogo maestro directamente.
    """
    db_path = get_db_path_local()
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    
    sku = product_in.master_sku.strip().upper()
    nombre = product_in.nombre_normalizado.strip().upper()
    barcode = product_in.codigo_barras.strip() if product_in.codigo_barras else None
    
    try:
        # Verificar duplicación de SKU
        existing_sku = session.query(CatalogoMaestro).filter(CatalogoMaestro.master_sku == sku).first()
        if existing_sku:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El SKU Maestro '{sku}' ya se encuentra registrado."
            )
            
        # Verificar duplicación de código de barras
        if barcode:
            existing_barcode = session.query(CatalogoMaestro).filter(CatalogoMaestro.codigo_barras == barcode).first()
            if existing_barcode:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El código de barras '{barcode}' ya está asignado al producto: {existing_barcode.nombre_normalizado}"
                )
                
        # Crear nuevo producto
        new_prod = CatalogoMaestro(
            master_sku=sku,
            codigo_barras=barcode,
            nombre_normalizado=nombre,
            marca=product_in.marca.strip().upper(),
            categoria=product_in.categoria.strip().upper(),
            precio_costo=product_in.precio_costo,
            margen_ganancia=product_in.margen_ganancia,
            precio_venta=round(product_in.precio_costo * (1 + product_in.margen_ganancia), 2)
        )
        session.add(new_prod)
        session.commit()
        return {
            "master_sku": new_prod.master_sku,
            "nombre_normalizado": new_prod.nombre_normalizado,
            "codigo_barras": new_prod.codigo_barras,
            "precio_venta": new_prod.precio_venta
        }
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar el producto: {e}"
        )
    finally:
        session.close()

@app.get("/api/coincidencias")
def get_pending_matches():
    """
    Retorna la lista de coincidencias dudosas pendientes de revisión con detalles comparativos.
    """
    db_path = get_db_path_local()
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    try:
        matches = session.query(CoincidenciaPendiente).filter(
            CoincidenciaPendiente.estado == 'PENDIENTE'
        ).order_by(CoincidenciaPendiente.similitud.desc()).all()
        
        results = []
        for m in matches:
            p_prov = session.query(ProductoProveedor).filter(ProductoProveedor.id == m.producto_proveedor_id).first()
            m_prod = session.query(CatalogoMaestro).filter(CatalogoMaestro.master_sku == m.master_sku_sugerido).first()
            
            if p_prov and m_prod:
                results.append({
                    "id": m.id,
                    "master_sku_sugerido": m.master_sku_sugerido,
                    "codigo_proveedor": p_prov.sku_proveedor,
                    "nombre_proveedor": p_prov.proveedor_id,
                    "nombre_catalogo": m_prod.nombre_normalizado,
                    "nombre_proveedor_producto": p_prov.nombre_original,
                    "similitud": round(m.similitud, 1),
                    "precio_crudo_proveedor": p_prov.precio_crudo or 0.0,
                    "costo_calculado_proveedor": p_prov.costo_calculado or 0.0,
                    "costo_actual_catalogo": m_prod.precio_costo or 0.0,
                    "venta_actual_catalogo": m_prod.precio_venta or 0.0,
                    "producto_proveedor_id": p_prov.id,
                    "archivo_origen": p_prov.archivo_origen or "Desconocido",
                    "marca_catalogo": m_prod.marca or "VARIOS",
                    "marca_proveedor": extract_brand(p_prov.nombre_original, session)
                })
        return results
    finally:
        session.close()

@app.post("/api/coincidencias/{match_id}/resolver")
def resolve_match_endpoint(match_id: int, resolve_in: ResolverMatch):
    """
    Resuelve (Aprobar o Rechazar) una coincidencia pendiente.
    """
    db_path = get_db_path_local()
    if resolve_in.action == "APROBAR":
        overrides = {
            "nombre_normalizado": resolve_in.nombre_normalizado,
            "marca": resolve_in.marca,
            "categoria": resolve_in.categoria,
            "precio_costo": resolve_in.precio_costo,
            "margen_ganancia": resolve_in.margen_ganancia,
            "codigo_barras": resolve_in.codigo_barras
        }
        # Filtrar valores nulos
        overrides = {k: v for k, v in overrides.items() if v is not None}
        success = approve_pending_match(match_id, db_path, overrides=overrides if overrides else None)
    else:
        success = reject_pending_match(match_id, db_path)
        
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se pudo resolver la coincidencia pendiente con ID {match_id}."
        )
    return {"status": "success", "message": f"Coincidencia {match_id} resuelta exitosamente ({resolve_in.action})."}

@app.post("/api/proveedor-producto/{prod_prov_id}/crear-nuevo")
def split_create_new_endpoint(prod_prov_id: int):
    """
    Desvincula un producto de proveedor de cualquier coincidencia y lo registra como un nuevo producto maestro.
    """
    db_path = get_db_path_local()
    new_sku = split_and_create_new(prod_prov_id, db_path)
    if not new_sku:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo crear el producto de proveedor ID {prod_prov_id} como nuevo."
        )
    
    # También removemos las coincidencias pendientes asociadas a este producto de proveedor
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    try:
        session.query(CoincidenciaPendiente).filter(
            CoincidenciaPendiente.producto_proveedor_id == prod_prov_id
        ).update({"estado": "RECHAZADO"})
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error rechazando coincidencias asociadas post-split: {e}")
    finally:
        session.close()

    return {"status": "success", "new_sku": new_sku, "message": f"Producto registrado como nuevo con SKU: {new_sku}"}


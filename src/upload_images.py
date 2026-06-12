#!/usr/bin/env python3
import os
import sys
import glob
import shutil
import requests
from sqlalchemy.orm import Session

# Set python path and working directory
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_dir)
if project_dir not in sys.path:
    sys.path.append(project_dir)

from src.utils.logger import setup_logger
from src.utils.helpers import load_config
from src.models import get_db_session, CatalogoMaestro

logger = setup_logger()

# Mapeo de extensiones de archivo a tipos MIME
MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp"
}

def upload_image_to_wp(image_path: str, url: str, wp_user: str, wp_pass: str) -> int:
    """
    Sube un archivo de imagen local a la biblioteca de medios de WordPress.
    Retorna el ID del medio subido (media_id) o None si falla.
    """
    ext = os.path.splitext(image_path)[1].lower()
    mime_type = MIME_TYPES.get(ext, "image/jpeg")
    filename = os.path.basename(image_path)
    
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": mime_type
    }
    
    try:
        with open(image_path, "rb") as f:
            media_bytes = f.read()
            
        endpoint = f"{url}/wp-json/wp/v2/media"
        response = requests.post(
            endpoint,
            data=media_bytes,
            headers=headers,
            auth=(wp_user, wp_pass),
            timeout=45
        )
        
        if response.status_code == 201:
            res_data = response.json()
            media_id = res_data.get("id")
            logger.info(f"  -> Imagen subida con éxito. WordPress Media ID: {media_id}")
            return media_id
        else:
            logger.error(f"  -> Error al subir imagen. Código {response.status_code}: {response.text}")
            return None
    except Exception as e:
        logger.error(f"  -> Excepción al subir imagen: {e}")
        return None

def associate_image_to_wc(product_id: int, media_id: int, url: str, wc_key: str, wc_secret: str) -> bool:
    """
    Asocia la imagen subida (media_id) al producto correspondiente de WooCommerce.
    """
    endpoint = f"{url}/wp-json/wc/v3/products/{product_id}"
    try:
        # Recuperar imágenes existentes en la web para no borrarlas al asociar la nueva
        get_response = requests.get(endpoint, auth=(wc_key, wc_secret), timeout=20)
        existing_images = []
        if get_response.status_code == 200:
            existing_images = get_response.json().get("images", [])
            
        # Si la imagen ya está asociada, evitamos duplicar la petición
        if any(img.get("id") == media_id for img in existing_images):
            return True
            
        new_images = existing_images + [{"id": media_id}]
        
        response = requests.put(
            endpoint,
            json={"images": new_images},
            auth=(wc_key, wc_secret),
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info(f"  -> Producto WooCommerce ID {product_id} actualizado con la nueva imagen.")
            return True
        else:
            logger.error(f"  -> Error al asociar imagen. Código {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"  -> Excepción al asociar imagen: {e}")
        return False

def main():
    config = load_config("config.yaml")
    
    # Configuración de rutas
    images_dir = config.get("paths", {}).get("images_dir", "data/images")
    db_path = config.get("paths", {}).get("db_path")
    
    # WooCommerce Config
    wc_config = config.get("woocommerce", {})
    url = wc_config.get("url", "").rstrip("/")
    consumer_key = wc_config.get("consumer_key", "")
    consumer_secret = wc_config.get("consumer_secret", "")
    dry_run = wc_config.get("dry_run", True)
    
    # WordPress Config
    wp_config = config.get("wordpress", {})
    wp_user = wp_config.get("username", "")
    wp_pass = wp_config.get("application_password", "")
    
    if not os.path.exists(images_dir):
        logger.info(f"Creando directorio de imágenes en: {images_dir}")
        os.makedirs(images_dir, exist_ok=True)
        
    processed_dir = os.path.join(images_dir, "processed")
    os.makedirs(processed_dir, exist_ok=True)
    
    # Buscar archivos de imagen soportados
    image_files = []
    for ext in MIME_TYPES.keys():
        image_files.extend(glob.glob(os.path.join(images_dir, f"*{ext}")))
        image_files.extend(glob.glob(os.path.join(images_dir, f"*{ext.upper()}")))
        
    logger.info(f"Encontrados {len(image_files)} archivos de imágenes en {images_dir} para procesar.")
    if not image_files:
        logger.info("No se encontraron imágenes para subir. Coloca tus imágenes nombradas por EAN o SKU en data/images/")
        return
        
    # Validar credenciales si no es una simulación
    if not dry_run:
        if not url or "reemplazar" in consumer_key or "reemplazar" in wp_pass:
            logger.error("Error: Las credenciales de WordPress o WooCommerce siguen configuradas con los marcadores de posición.")
            logger.error("Por favor completa las credenciales reales en config.yaml antes de continuar.")
            sys.exit(1)
            
    SessionFactory = get_db_session(db_path)
    session: Session = SessionFactory()
    
    success_count = 0
    fail_count = 0
    
    try:
        for img_path in image_files:
            filename = os.path.basename(img_path)
            # Extraer identificador sin extensión
            identifier = os.path.splitext(filename)[0].strip()
            
            logger.info(f"\nProcesando imagen: '{filename}' (Identificador: '{identifier}')...")
            
            # Buscar producto por Código de Barras o SKU Maestro
            product = session.query(CatalogoMaestro).filter(
                (CatalogoMaestro.codigo_barras == identifier) | 
                (CatalogoMaestro.master_sku == identifier.upper())
            ).first()
            
            if not product:
                logger.warning(f"  -> Omitida: No se encontró ningún producto en el catálogo maestro con EAN o SKU: '{identifier}'")
                continue
                
            if not product.id_woocommerce:
                logger.warning(f"  -> Omitida: El producto '{product.master_sku}' no está mapeado en WooCommerce (ID_WooCommerce nulo).")
                continue
                
            logger.info(f"  -> Producto encontrado: {product.nombre_normalizado} (WooCommerce ID: {product.id_woocommerce})")
            
            if dry_run:
                logger.info(f"  -> [SIMULACIÓN] Se subiría a WordPress y se asociaría al producto ID {product.id_woocommerce}")
                success_count += 1
                continue
                
            # Modo Producción: Subir y asociar
            media_id = upload_image_to_wp(img_path, url, wp_user, wp_pass)
            if media_id:
                associated = associate_image_to_wc(product.id_woocommerce, media_id, url, consumer_key, consumer_secret)
                if associated:
                    success_count += 1
                    # Mover archivo procesado para evitar reprocesamientos
                    dest_path = os.path.join(processed_dir, filename)
                    if os.path.exists(dest_path):
                        import time
                        dest_path = os.path.join(processed_dir, f"{identifier}_{int(time.time())}{os.path.splitext(filename)[1]}")
                    shutil.move(img_path, dest_path)
                    logger.info(f"  -> Archivo movido a la carpeta 'processed'.")
                else:
                    fail_count += 1
            else:
                fail_count += 1
                
        logger.info(f"\nProceso completado. Exitosos: {success_count}, Fallidos: {fail_count}")
        
    except Exception as e:
        logger.error(f"Error crítico en el bucle principal de imágenes: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    main()

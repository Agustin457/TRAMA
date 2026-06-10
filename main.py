#!/usr/bin/env python3
"""
Orquestador Principal del Pipeline ETL de Automatización - Proyecto Trama
"""
import sys
import os
from src.utils.logger import setup_logger
from src.utils.helpers import load_config
from src.models import init_db
from src.migrate_woocommerce import migrate_woocommerce_csv
from src.import_providers import import_supplier_data
from src.matching import run_matching_engine
from src.transform import consolidate_master_catalog
from src.load import load_to_csv, load_to_excel

def main():
    # Establecer el directorio de trabajo al directorio de este script
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    # 1. Inicializar logger por defecto
    logger = setup_logger(name="etl_pipeline", log_level="INFO")
    logger.info("==========================================")
    logger.info("Iniciando Proceso ETL - Fase 1: Catálogo Maestro")
    logger.info("==========================================")
    
    try:
        # 2. Cargar configuración
        logger.info("Cargando configuraciones desde config.yaml...")
        config = load_config("config.yaml")
        
        # Actualizar el nivel de log con el valor de la configuración
        log_level = config.get("pipeline", {}).get("log_level", "INFO")
        logger = setup_logger(name="etl_pipeline", log_level=log_level)
        
        # Rutas de Base de Datos y WooCommerce
        db_path = config.get("paths", {}).get("db_path", "data/etl_database.db")
        woocommerce_csv = config.get("paths", {}).get("woocommerce_csv_path", "data/raw/woocommerce_products.csv")
        output_dir = config.get("paths", {}).get("output_dir", "data/output")
        master_name = config.get("paths", {}).get("master_output_name", "productos_master")
        
        # A. Inicializar base de datos
        logger.info("Inicializando Base de Datos SQLite...")
        init_db(db_path)
        
        # B. Ingesta de WooCommerce CSV
        logger.info("Ejecutando migración inicial de WooCommerce CSV...")
        migrate_woocommerce_csv(woocommerce_csv, db_path)

        # C. Importar datos de cada proveedor
        logger.info("Ejecutando Ingesta de Proveedores...")
        providers = config.get("extraction", {}).get("providers", {})
        for prov_name in providers.keys():
            logger.info(f"Procesando proveedor: {prov_name.upper()}...")
            import_supplier_data(prov_name, db_path=db_path)
        
        # D. Ejecutar motor de matching y deduplicación semántica
        logger.info("Ejecutando Motor de Matching Inteligente...")
        matching_results = run_matching_engine(db_path)
        logger.info(f"Resultados de Matching: {matching_results}")
        
        # E. Consolidar catálogo maestro (Stock, Precios, Costos)
        logger.info("Consolidando Catálogo Maestro...")
        df_master = consolidate_master_catalog(db_path)
        
        # F. Exportar catálogo unificado
        csv_output_path = os.path.join(output_dir, f"{master_name}.csv")
        excel_output_path = os.path.join(output_dir, f"{master_name}.xlsx")
        
        logger.info(f"Exportando Catálogo Maestro consolidado a {csv_output_path}...")
        load_to_csv(df_master, csv_output_path)
        
        logger.info(f"Exportando Catálogo Maestro consolidado a {excel_output_path}...")
        load_to_excel(df_master, excel_output_path)
        
        logger.info("==========================================")
        logger.info("Proceso ETL finalizado exitosamente!")
        logger.info("==========================================")
        
    except Exception as e:
        logger.critical(f"El Pipeline falló debido a un error crítico: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()

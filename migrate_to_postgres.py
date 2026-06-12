#!/usr/bin/env python3
import sys
import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_values

# Set working directory to the script's directory and add it to sys.path
project_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_dir)
if project_dir not in sys.path:
    sys.path.append(project_dir)

from src.utils.helpers import load_config

def migrate():
    print("Cargando configuración...")
    config = load_config("config.yaml")
    
    sqlite_path = "data/etl_database.db"
    postgres_uri = config.get("paths", {}).get("db_path")
    
    if "sqlite" in postgres_uri:
        print("ERROR: La ruta 'db_path' en config.yaml sigue apuntando a SQLite.")
        sys.exit(1)
        
    if "[YOUR-PASSWORD]" in postgres_uri:
        print("ERROR: La URI de Supabase en config.yaml contiene el marcador '[YOUR-PASSWORD]'.")
        sys.exit(1)

    print(f"Origen (SQLite): {sqlite_path}")
    print(f"Destino (PostgreSQL): {postgres_uri.split('@')[-1]}")
    
    if not os.path.exists(sqlite_path):
        print(f"ERROR: No se encontró la base de datos de origen en '{sqlite_path}'.")
        sys.exit(1)

    # 1. Connect to Postgres
    print("\nConectando a PostgreSQL (Supabase)...")
    pg_conn = psycopg2.connect(postgres_uri)
    pg_cur = pg_conn.cursor()
    
    # 2. Connect to SQLite
    print("Conectando a SQLite...")
    lite_conn = sqlite3.connect(sqlite_path)
    lite_cur = lite_conn.cursor()
    
    try:
        # 3. Clean target tables first (Cascade to handle FK constraints)
        print("\nLimpiando tablas de destino en Supabase (TRUNCATE CASCADE)...")
        pg_cur.execute("""
            TRUNCATE TABLE 
                proveedores, 
                catalogo_maestro, 
                productos_proveedor, 
                coincidencias_pendientes, 
                historial_precios, 
                auditoria_unificacion 
            RESTART IDENTITY CASCADE;
        """)
        pg_conn.commit()
        print("-> Tablas truncadas exitosamente.")
        
        tables = [
            {
                "name": "proveedores",
                "columns": ["id", "nombre", "margen_defecto"]
            },
            {
                "name": "catalogo_maestro",
                "columns": ["master_sku", "codigo_barras", "nombre_normalizado", "marca", "categoria", "precio_costo", "margen_ganancia", "precio_venta", "id_woocommerce", "last_updated"]
            },
            {
                "name": "productos_proveedor",
                "columns": ["id", "proveedor_id", "sku_proveedor", "nombre_original", "precio_crudo", "costo_calculado", "stock_crudo", "codigo_barras", "master_sku", "estado_unificacion", "archivo_origen", "last_imported_at"]
            },
            {
                "name": "coincidencias_pendientes",
                "columns": ["id", "producto_proveedor_id", "master_sku_sugerido", "similitud", "estado", "created_at"]
            },
            {
                "name": "historial_precios",
                "columns": ["id", "producto_proveedor_id", "precio_crudo_anterior", "precio_crudo_nuevo", "costo_calculado_anterior", "costo_calculado_nuevo", "fecha_actualizacion"]
            },
            {
                "name": "auditoria_unificacion",
                "columns": ["id", "producto_proveedor_id", "master_sku", "accion", "score_similitud", "detalles", "fecha"]
            }
        ]
        
        for t in tables:
            name = t["name"]
            cols = t["columns"]
            print(f"\nMigrando tabla: {name}...")
            
            # Read from SQLite
            lite_cur.execute(f"SELECT {', '.join(cols)} FROM {name}")
            rows = lite_cur.fetchall()
            print(f"-> Se encontraron {len(rows)} registros en SQLite.")
            
            if not rows:
                print("-> Omitiendo (sin datos).")
                continue
                
            # Bulk Insert using psycopg2 execute_values (ultra fast)
            query = f"INSERT INTO {name} ({', '.join(cols)}) VALUES %s"
            execute_values(pg_cur, query, rows)
            pg_conn.commit()
            print(f"-> Insertados exitosamente {len(rows)} registros en {name} (Supabase).")
            
        print("\n=============================================")
        print("¡MIGRACIÓN COMPLETADA CON ÉXITO EN SEGUNDOS!")
        print("=============================================")
        
    except Exception as e:
        pg_conn.rollback()
        print(f"\nERROR CRÍTICO durante la migración: {e}")
        raise
    finally:
        pg_cur.close()
        pg_conn.close()
        lite_cur.close()
        lite_conn.close()

if __name__ == "__main__":
    migrate()

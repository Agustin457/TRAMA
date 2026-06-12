#!/usr/bin/env python3
"""
Script de Migración de Catálogo: SQLite -> PostgreSQL (Supabase)
"""
import sys
import os
from sqlalchemy.orm import Session
from src.utils.helpers import load_config
from src.models import (
    init_db, get_db_session, 
    Proveedor, CatalogoMaestro, ProductoProveedor, 
    CoincidenciaPendiente, HistorialPrecio, AuditoriaUnificacion
)

def migrate():
    # Establecer el directorio de trabajo al del script
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    print("Cargando configuración...")
    config = load_config("config.yaml")
    
    sqlite_path = "data/etl_database.db"
    postgres_uri = config.get("paths", {}).get("db_path")
    
    if "sqlite" in postgres_uri:
        print("ERROR: La ruta 'db_path' en config.yaml sigue apuntando a SQLite.")
        print("Por favor actualízala con tu URI de Supabase antes de correr la migración.")
        sys.exit(1)
        
    if "[YOUR-PASSWORD]" in postgres_uri:
        print("ERROR: La URI de Supabase en config.yaml contiene el marcador '[YOUR-PASSWORD]'.")
        print("Por favor reemplaza '[YOUR-PASSWORD]' por la contraseña real de tu base de datos.")
        sys.exit(1)

    print(f"Origen (SQLite): {sqlite_path}")
    print(f"Destino (PostgreSQL): {postgres_uri.split('@')[-1]}") # Ocultar pass en logs
    
    if not os.path.exists(sqlite_path):
        print(f"ERROR: No se encontró la base de datos de origen en '{sqlite_path}'.")
        print("Por favor ejecuta primero 'python main.py' con la configuración local de SQLite para generar datos.")
        sys.exit(1)

    # 1. Inicializar esquema de tablas en PostgreSQL
    print("\nInicializando tablas en Supabase/PostgreSQL...")
    init_db(postgres_uri)
    
    # 2. Abrir sesiones
    SQLiteSession = get_db_session(f"sqlite:///{sqlite_path}")
    PostgresSession = get_db_session(postgres_uri)
    
    src_session: Session = SQLiteSession()
    dst_session: Session = PostgresSession()
    
    try:
        # A. Copiar Proveedores
        print("Migrando tabla 'proveedores'...")
        provs = src_session.query(Proveedor).all()
        for p in provs:
            # Evitar duplicados
            if not dst_session.query(Proveedor).filter(Proveedor.id == p.id).first():
                dst_session.add(Proveedor(id=p.id, nombre=p.nombre, margen_defecto=p.margen_defecto))
        dst_session.commit()

        # B. Copiar CatalogoMaestro
        print("Migrando tabla 'catalogo_maestro'...")
        master_items = src_session.query(CatalogoMaestro).all()
        for item in master_items:
            if not dst_session.query(CatalogoMaestro).filter(CatalogoMaestro.master_sku == item.master_sku).first():
                dst_session.add(CatalogoMaestro(
                    master_sku=item.master_sku,
                    codigo_barras=item.codigo_barras,
                    nombre_normalizado=item.nombre_normalizado,
                    marca=item.marca,
                    categoria=item.categoria,
                    precio_costo=item.precio_costo,
                    margen_ganancia=item.margen_ganancia,
                    precio_venta=item.precio_venta,
                    id_woocommerce=item.id_woocommerce,
                    last_updated=item.last_updated
                ))
        dst_session.commit()

        # C. Copiar ProductoProveedor
        print("Migrando tabla 'productos_proveedor'...")
        pp_items = src_session.query(ProductoProveedor).all()
        for pp in pp_items:
            # Buscar por id o por sku_proveedor + proveedor_id para evitar duplicar
            existing = dst_session.query(ProductoProveedor).filter(
                ProductoProveedor.proveedor_id == pp.proveedor_id,
                ProductoProveedor.sku_proveedor == pp.sku_proveedor
            ).first()
            if not existing:
                dst_session.add(ProductoProveedor(
                    id=pp.id,
                    proveedor_id=pp.proveedor_id,
                    sku_proveedor=pp.sku_proveedor,
                    nombre_original=pp.nombre_original,
                    precio_crudo=pp.precio_crudo,
                    costo_calculado=pp.costo_calculado,
                    stock_crudo=pp.stock_crudo,
                    codigo_barras=pp.codigo_barras,
                    master_sku=pp.master_sku,
                    estado_unificacion=pp.estado_unificacion,
                    archivo_origen=pp.archivo_origen,
                    last_imported_at=pp.last_imported_at
                ))
        dst_session.commit()

        # D. Copiar CoincidenciasPendientes
        print("Migrando tabla 'coincidencias_pendientes'...")
        pending = src_session.query(CoincidenciaPendiente).all()
        for cp in pending:
            existing = dst_session.query(CoincidenciaPendiente).filter(
                CoincidenciaPendiente.producto_proveedor_id == cp.producto_proveedor_id,
                CoincidenciaPendiente.master_sku_sugerido == cp.master_sku_sugerido
            ).first()
            if not existing:
                dst_session.add(CoincidenciaPendiente(
                    id=cp.id,
                    producto_proveedor_id=cp.producto_proveedor_id,
                    master_sku_sugerido=cp.master_sku_sugerido,
                    similitud=cp.similitud,
                    estado=cp.estado,
                    created_at=cp.created_at
                ))
        dst_session.commit()

        # E. Copiar HistorialPrecios
        print("Migrando tabla 'historial_precios'...")
        hist = src_session.query(HistorialPrecio).all()
        for h in hist:
            dst_session.add(HistorialPrecio(
                producto_proveedor_id=h.producto_proveedor_id,
                precio_crudo_anterior=h.precio_crudo_anterior,
                precio_crudo_nuevo=h.precio_crudo_nuevo,
                costo_calculado_anterior=h.costo_calculado_anterior,
                costo_calculado_nuevo=h.costo_calculado_nuevo,
                fecha_actualizacion=h.fecha_actualizacion
            ))
        dst_session.commit()

        # F. Copiar AuditoriaUnificacion
        print("Migrando tabla 'auditoria_unificacion'...")
        audits = src_session.query(AuditoriaUnificacion).all()
        for au in audits:
            dst_session.add(AuditoriaUnificacion(
                producto_proveedor_id=au.producto_proveedor_id,
                master_sku=au.master_sku,
                accion=au.accion,
                score_similitud=au.score_similitud,
                detalles=au.detalles,
                fecha=au.fecha
            ))
        dst_session.commit()

        print("\n=======================================================")
        print("¡MIGRACIÓN DE DATOS A POSTGRESQL FINALIZADA CON ÉXITO!")
        print("=======================================================")

    except Exception as e:
        dst_session.rollback()
        print(f"\nERROR CRÍTICO durante la migración: {e}")
        raise
    finally:
        src_session.close()
        dst_session.close()

if __name__ == "__main__":
    migrate()

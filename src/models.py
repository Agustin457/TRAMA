import os
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Float, Integer, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from src.utils.helpers import load_config

Base = declarative_base()

class Proveedor(Base):
    __tablename__ = 'proveedores'
    
    id = Column(String(50), primary_key=True)  # 'ALE', 'POWERLAND', 'ROTRING'
    nombre = Column(String(100), nullable=False)
    margen_defecto = Column(Float, default=0.40)
    
    productos = relationship("ProductoProveedor", back_populates="proveedor")

    def __repr__(self):
        return f"<Proveedor(id='{self.id}', nombre='{self.nombre}')>"

class CatalogoMaestro(Base):
    __tablename__ = 'catalogo_maestro'

    master_sku = Column(String(100), primary_key=True)  # SKU estructurado: ESC-BIC-CRIS-AZU
    codigo_barras = Column(String(100), nullable=True, index=True)
    nombre_normalizado = Column(String(255), nullable=False)
    marca = Column(String(100), nullable=False, index=True)
    categoria = Column(String(100), nullable=False, index=True)
    precio_costo = Column(Float, default=0.0, nullable=False)
    margen_ganancia = Column(Float, default=0.40, nullable=False)
    precio_venta = Column(Float, default=0.0, nullable=False)
    id_woocommerce = Column(Integer, nullable=True, index=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    productos_proveedor = relationship("ProductoProveedor", back_populates="catalogo_maestro")

    def __repr__(self):
        return f"<CatalogoMaestro(master_sku='{self.master_sku}', nombre='{self.nombre_normalizado}', precio_venta={self.precio_venta})>"

class ProductoProveedor(Base):
    __tablename__ = 'productos_proveedor'

    id = Column(Integer, primary_key=True, autoincrement=True)
    proveedor_id = Column(String(50), ForeignKey('proveedores.id'), nullable=False, index=True)
    sku_proveedor = Column(String(100), nullable=False, index=True)  # Código original del proveedor
    nombre_original = Column(String(255), nullable=False)
    precio_crudo = Column(Float, nullable=False)  # Precio bruto del Excel
    costo_calculado = Column(Float, nullable=False)  # Costo neto neto con impuestos aplicados
    stock_crudo = Column(Integer, default=0, nullable=False)
    codigo_barras = Column(String(100), nullable=True, index=True)
    master_sku = Column(String(100), ForeignKey('catalogo_maestro.master_sku'), nullable=True, index=True)
    estado_unificacion = Column(String(50), default='PENDIENTE', nullable=False, index=True)  # 'PENDIENTE', 'APROBADO', 'NUEVO_PRODUCTO'
    last_imported_at = Column(DateTime, default=datetime.utcnow)

    proveedor = relationship("Proveedor", back_populates="productos")
    catalogo_maestro = relationship("CatalogoMaestro", back_populates="productos_proveedor")
    coincidencias = relationship("CoincidenciaPendiente", back_populates="producto_proveedor", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ProductoProveedor(id={self.id}, proveedor='{self.proveedor_id}', sku='{self.sku_proveedor}', nombre='{self.nombre_original[:30]}', cost={self.costo_calculado})>"

class CoincidenciaPendiente(Base):
    __tablename__ = 'coincidencias_pendientes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    producto_proveedor_id = Column(Integer, ForeignKey('productos_proveedor.id'), nullable=False, index=True)
    master_sku_sugerido = Column(String(100), ForeignKey('catalogo_maestro.master_sku'), nullable=False, index=True)
    similitud = Column(Float, nullable=False)
    estado = Column(String(50), default='PENDIENTE', nullable=False, index=True)  # 'PENDIENTE', 'APROBADO', 'RECHAZADO'
    created_at = Column(DateTime, default=datetime.utcnow)

    producto_proveedor = relationship("ProductoProveedor", back_populates="coincidencias")
    catalogo_maestro = relationship("CatalogoMaestro")

    def __repr__(self):
        return f"<CoincidenciaPendiente(id={self.id}, prod_prov_id={self.producto_proveedor_id}, sugerencia='{self.master_sku_sugerido}', score={self.similitud}%)>"

class HistorialPrecio(Base):
    __tablename__ = 'historial_precios'

    id = Column(Integer, primary_key=True, autoincrement=True)
    producto_proveedor_id = Column(Integer, ForeignKey('productos_proveedor.id'), nullable=False, index=True)
    precio_crudo_anterior = Column(Float, nullable=False)
    precio_crudo_nuevo = Column(Float, nullable=False)
    costo_calculado_anterior = Column(Float, nullable=False)
    costo_calculado_nuevo = Column(Float, nullable=False)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<HistorialPrecio(id={self.id}, prod_prov_id={self.producto_proveedor_id}, costo_nuevo={self.costo_calculado_nuevo})>"

class AuditoriaUnificacion(Base):
    __tablename__ = 'auditoria_unificacion'

    id = Column(Integer, primary_key=True, autoincrement=True)
    producto_proveedor_id = Column(Integer, ForeignKey('productos_proveedor.id'), nullable=False, index=True)
    master_sku = Column(String(100), nullable=False, index=True)
    accion = Column(String(50), nullable=False)  # 'AUTO_MERGE', 'MANUAL_MERGE', 'SPLIT', 'REJECTED_MERGE'
    score_similitud = Column(Float, nullable=False)
    detalles = Column(String(1000), nullable=True)  # JSON o texto explicativo
    fecha = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AuditoriaUnificacion(id={self.id}, master_sku='{self.master_sku}', accion='{self.accion}')>"

# Funciones de utilidad para base de datos

def get_db_path() -> str:
    """
    Obtiene la ruta de la base de datos desde la configuración.
    """
    try:
        config = load_config("config.yaml")
        return config.get("paths", {}).get("db_path", "data/etl_database.db")
    except Exception:
        return "data/etl_database.db"

def get_db_engine(db_path: str = None):
    """
    Crea y retorna el engine de SQLAlchemy para la base de datos SQLite.
    """
    if db_path is None:
        db_path = get_db_path()
        
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        
    return create_engine(f"sqlite:///{db_path}", echo=False)

def init_db(db_path: str = None) -> None:
    """
    Inicializa la base de datos creando todas las tablas definidas y poblando proveedores.
    """
    engine = get_db_engine(db_path)
    Base.metadata.create_all(engine)
    
    # Poblar proveedores por defecto si no existen
    SessionClass = sessionmaker(bind=engine)
    session = SessionClass()
    try:
        default_providers = [
            Proveedor(id='ALE', nombre='Librería ALE', margen_defecto=0.40),
            Proveedor(id='POWERLAND', nombre='Powerland SRL', margen_defecto=0.40),
            Proveedor(id='ROTRING', nombre='Rotring / Plantec', margen_defecto=0.40)
        ]
        for prov in default_providers:
            existing = session.query(Proveedor).filter(Proveedor.id == prov.id).first()
            if not existing:
                session.add(prov)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error inicializando proveedores: {e}")
    finally:
        session.close()

def get_db_session(db_path: str = None) -> sessionmaker:
    """
    Retorna un creador de sesiones (sessionmaker) vinculado a la base de datos.
    """
    engine = get_db_engine(db_path)
    return sessionmaker(bind=engine)

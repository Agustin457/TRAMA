import pytest
from fastapi.testclient import TestClient
from src.app import app
from src.models import get_db_session, init_db, CatalogoMaestro, ProductoProveedor, Proveedor

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_db_path = "sqlite:///data/test_app_database.db"
    monkeypatch.setattr("src.app.get_db_path_local", lambda: test_db_path)
    
    init_db(test_db_path)
    
    SessionFactory = get_db_session(test_db_path)
    session = SessionFactory()
    try:
        session.query(ProductoProveedor).delete()
        session.query(CatalogoMaestro).delete()
        session.query(Proveedor).delete()
        
        session.add(Proveedor(id='LOCAL', nombre='Stock Local', margen_defecto=0.60))
        session.add(Proveedor(id='ROTRING', nombre='Rotring', margen_defecto=0.60))
        
        m_prod = CatalogoMaestro(
            master_sku="TEST-SKU",
            codigo_barras="1234567890",
            nombre_normalizado="PRODUCTO DE PRUEBA",
            marca="BIC",
            categoria="VARIOS",
            precio_costo=100.0,
            margen_ganancia=0.60,
            precio_venta=160.0
        )
        session.add(m_prod)
        session.commit()
    finally:
        session.close()

def test_get_product_by_barcode():
    response = client.get("/api/producto/1234567890")
    assert response.status_code == 200
    data = response.json()
    assert data["master_sku"] == "TEST-SKU"
    assert data["stock_total"] == 0

def test_register_stock_intake():
    response = client.post("/api/producto/ingreso", json={
        "codigo_barras": "1234567890",
        "proveedor_id": "LOCAL",
        "cantidad": 10,
        "precio_costo": 200.0
    })
    assert response.status_code == 200
    data = response.json()
    assert data["stock_total"] == 10
    assert data["precio_costo"] == 200.0
    assert data["precio_venta"] == 320.0

def test_register_stock_intake_rotring_iva():
    response = client.post("/api/producto/ingreso", json={
        "master_sku": "TEST-SKU",
        "proveedor_id": "ROTRING",
        "cantidad": 5,
        "precio_costo": 100.0
    })
    assert response.status_code == 200
    data = response.json()
    assert data["stock_total"] == 5
    assert data["precio_costo"] == 121.0
    assert data["precio_venta"] == 193.6

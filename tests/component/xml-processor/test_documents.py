"""
Component tests: xml-processor — listado de documentos y catálogos.
Servicios externos mockeados; Postgres real.
"""

from fastapi.testclient import TestClient


def test_list_documents_empty(client: TestClient):
    # `from_date` y `to_date` son obligatorios en el endpoint: listar sin acotar el rango
    # significaría recorrer la tabla entera de un tenant en produccion. El test los omitia y
    # recibia 422, no la lista vacia que esperaba comprobar.
    r = client.get("/api/v1/documents", params={"from_date": "2026-01-01", "to_date": "2026-12-31"})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body or isinstance(body, list)


def test_list_receivers_empty(client: TestClient):
    r = client.get("/api/v1/receivers")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_catalog_cost_centers_empty(client: TestClient):
    r = client.get("/api/v1/catalog/cost-centers")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_catalog_puc_accounts_empty(client: TestClient):
    r = client.get("/api/v1/catalog/puc-accounts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_document_not_found(client: TestClient):
    r = client.get("/api/v1/documents/99999")
    assert r.status_code == 404


def test_health_check(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200

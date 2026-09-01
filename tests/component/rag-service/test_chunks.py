"""
Component tests: rag-service — indexar y buscar chunks.
Ollama mockeado; Postgres+pgvector real.
"""

from fastapi.testclient import TestClient


def test_index_chunk_returns_201(client: TestClient):
    r = client.post(
        "/api/v1/chunks",
        json={
            "source_type": "invoice",
            "source_id": 1,
            "content": "Factura de compra proveedor ABC",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["source_type"] == "invoice"
    assert body["id"] > 0


def test_index_chunk_without_source_id(client: TestClient):
    r = client.post(
        "/api/v1/chunks",
        json={"source_type": "file", "content": "Contrato de servicios generales"},
    )
    assert r.status_code == 201
    assert r.json()["source_id"] is None


def test_search_returns_results(client: TestClient):
    client.post(
        "/api/v1/chunks",
        json={"source_type": "invoice", "source_id": 2, "content": "IVA factura septiembre"},
    )
    r = client.post("/api/v1/chunks/search", json={"query": "IVA factura", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert isinstance(body["results"], list)


def test_health_check(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200

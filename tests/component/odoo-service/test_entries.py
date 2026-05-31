"""
Component tests: odoo-service — listado de asientos contables.
Odoo XML-RPC y rag-service mockeados; Postgres real.
"""

from fastapi.testclient import TestClient


def test_list_entries_empty(client: TestClient):
    r = client.get("/api/v1/odoo/entries")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_health_check(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"

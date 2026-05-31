"""
Component tests: siigo-service — plan de cuentas y parámetros.
SIIGO API mockeado con respx; Postgres real.
"""

from fastapi.testclient import TestClient


def test_list_chart_accounts_empty(client: TestClient):
    r = client.get("/api/v1/siigo/chart-accounts")
    assert r.status_code in (200, 404)


def test_list_purchase_invoice_parameters_empty(client: TestClient):
    r = client.get("/api/v1/siigo/purchase-invoice-parameters")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_health_check(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200

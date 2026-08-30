"""
Component tests: integration-config-service — gestión de credenciales.
Cubre el ciclo completo PUT → GET sin dependencias externas.
"""

from fastapi.testclient import TestClient

PAYLOAD = {
    "provider": "siigo",
    "account_key": "empresa-test",
    "username": "api@test.com",
    "access_key": "clave-secreta-123",
    "base_url": "https://api.siigo.com",
    "auth_scheme": "oauth_jwt",
    "extra_config": {},
}


def test_upsert_credential_returns_200(client: TestClient):
    r = client.put("/api/v1/integrations/credentials", json=PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "siigo"
    assert body["username"] == "api@test.com"
    assert "access_key" not in body  # secreto no expuesto


def test_list_credentials_returns_created_entry(client: TestClient):
    client.put("/api/v1/integrations/credentials", json=PAYLOAD)
    r = client.get("/api/v1/integrations/credentials?provider=siigo")
    assert r.status_code == 200
    items = r.json()
    assert any(c["provider"] == "siigo" for c in items)


def test_upsert_is_idempotent(client: TestClient):
    r1 = client.put("/api/v1/integrations/credentials", json=PAYLOAD)
    r2 = client.put(
        "/api/v1/integrations/credentials", json={**PAYLOAD, "username": "nuevo@test.com"}
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["username"] == "nuevo@test.com"


def test_health_check(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"

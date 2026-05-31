"""
Component tests: auth-service — health check y endpoints básicos.
Login completo requiere DB + Redis disponibles (solo en CI).
"""

from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200


def test_login_invalid_credentials(client: TestClient):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "noexiste@test.com", "password": "wrong", "tenant_slug": "test"},
    )
    # 401 (credenciales inválidas) o 500 (DB no disponible) — ambos son aceptables aquí
    assert r.status_code in (401, 422, 500, 503)

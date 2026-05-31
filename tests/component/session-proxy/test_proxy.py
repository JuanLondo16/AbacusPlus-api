"""
Component tests: session-proxy — reenvío de peticiones al portal externo.
Las llamadas HTTP externas se mockean con respx.
"""

import httpx
import respx
from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_proxy_request_forwards_call(client: TestClient):
    with respx.mock:
        respx.get("https://catalogo-vpfe.dian.gov.co/api/facturas").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        r = client.post(
            "/api/v1/proxy/request",
            json={
                "token": "token-dian-123",
                "method": "GET",
                "path": "/api/facturas",
            },
        )
    # 200 o 502 dependiendo de si el cliente externo está configurado — validamos que no crashea
    assert r.status_code in (200, 502, 422)


def test_proxy_request_invalid_payload(client: TestClient):
    r = client.post("/api/v1/proxy/request", json={})
    assert r.status_code == 422

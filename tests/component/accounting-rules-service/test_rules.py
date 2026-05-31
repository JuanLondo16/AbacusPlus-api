"""
Component tests: accounting-rules-service — ciclo de reglas de causación.
Ollama mockeado; Postgres+pgvector real.
"""

from fastapi.testclient import TestClient

RULE_PAYLOAD = {
    "issuer_nit": "900123456",
    "match_key_type": "nit_only",
    "suggested_entries": [
        {"account_code": "2205", "account_name": "Proveedores", "debit": 0, "credit": 1000000},
        {"account_code": "1110", "account_name": "Bancos", "debit": 1000000, "credit": 0},
    ],
    "confidence_score": 0.9,
    "description": "Pago a proveedor ABC",
}


def test_create_rule_returns_201(client: TestClient):
    r = client.post("/api/v1/rules", json=RULE_PAYLOAD)
    assert r.status_code == 201
    body = r.json()
    assert body["issuer_nit"] == "900123456"
    assert body["id"] > 0


def test_list_rules_returns_created(client: TestClient):
    client.post("/api/v1/rules", json=RULE_PAYLOAD)
    r = client.get("/api/v1/rules?nit=900123456")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_lookup_returns_hit_or_miss(client: TestClient):
    client.post("/api/v1/rules", json=RULE_PAYLOAD)
    r = client.post(
        "/api/v1/rules/lookups",
        json={
            "issuer_nit": "900123456",
            "description": "Pago a proveedor ABC",
            "amount": 1000000,
        },
    )
    assert r.status_code == 200
    assert r.json()["result"] in ("HIT", "PARTIAL", "MISS")


def test_health_check(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200

"""
Component tests: llm-service — gestión de prompts del sistema.
No requiere llamadas externas — solo base de datos.
"""

from fastapi.testclient import TestClient

PROMPT_PAYLOAD = {
    "name": "PUC Colombia Test",
    "content": (
        "Eres un experto en contabilidad colombiana. " 'Responde con JSON: {"entries": [...]}'
    ),
}


def test_create_system_prompt(client: TestClient):
    r = client.post("/api/v1/accounting/system-prompts", json=PROMPT_PAYLOAD)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "PUC Colombia Test"
    assert body["id"] > 0


def test_list_system_prompts(client: TestClient):
    client.post("/api/v1/accounting/system-prompts", json=PROMPT_PAYLOAD)
    r = client.get("/api/v1/accounting/system-prompts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_activate_system_prompt(client: TestClient):
    create_r = client.post("/api/v1/accounting/system-prompts", json=PROMPT_PAYLOAD)
    prompt_id = create_r.json()["id"]
    r = client.patch(f"/api/v1/accounting/system-prompts/{prompt_id}", json={"is_active": True})
    assert r.status_code == 200
    assert r.json()["is_active"] is True


def test_health_check(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200

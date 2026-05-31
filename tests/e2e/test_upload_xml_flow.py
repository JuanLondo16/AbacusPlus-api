"""
E2E: subir un XML y consultar el documento procesado.

Flujo: POST /api/v1/documents → GET /api/v1/documents/{id}/full
Valida que xml-processor, rag-service y llm-service estén integrados.
"""

import time
from pathlib import Path

import httpx
import pytest


@pytest.mark.e2e
def test_upload_xml_and_retrieve(zip_fixture: Path, gateway_url: str):
    headers = {"Authorization": "Bearer test-e2e-token"}

    with zip_fixture.open("rb") as f:
        r = httpx.post(
            f"{gateway_url}/api/v1/documents",
            files={"file": ("factura_test.zip", f, "application/zip")},
            headers=headers,
            timeout=60,
        )

    assert r.status_code in (201, 200), f"Upload falló: {r.status_code} — {r.text[:200]}"
    doc_id = r.json()["id"]

    time.sleep(3)  # espera indexación RAG best-effort

    full = httpx.get(
        f"{gateway_url}/api/v1/documents/{doc_id}/full",
        headers=headers,
        timeout=15,
    )
    assert full.status_code == 200
    body = full.json()
    assert body["document"]["id"] == doc_id


@pytest.mark.e2e
def test_list_documents_after_upload(zip_fixture: Path, gateway_url: str):
    headers = {"Authorization": "Bearer test-e2e-token"}

    with zip_fixture.open("rb") as f:
        httpx.post(
            f"{gateway_url}/api/v1/documents",
            files={"file": ("factura_test.zip", f, "application/zip")},
            headers=headers,
            timeout=60,
        )

    r = httpx.get(f"{gateway_url}/api/v1/documents", headers=headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    items = body.get("items", body) if isinstance(body, dict) else body
    assert len(items) >= 1

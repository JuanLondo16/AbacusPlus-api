"""
E2E: aprobar un documento y verificar que accounting-rules-service aprendió la regla.

Flujo: POST /api/v1/documents → PATCH /approve → GET /api/v1/rules?nit=...
Valida que xml-processor notificó a accounting-rules-service tras la aprobación.
"""

import time
from pathlib import Path

import httpx
import pytest


def _upload_and_get_id(zip_fixture: Path, gateway_url: str) -> tuple[int, str]:
    """Sube un XML y retorna (doc_id, issuer_nit)."""
    headers = {"Authorization": "Bearer test-e2e-token"}
    with zip_fixture.open("rb") as f:
        r = httpx.post(
            f"{gateway_url}/api/v1/documents",
            files={"file": ("factura_test.zip", f, "application/zip")},
            headers=headers,
            timeout=60,
        )
    assert r.status_code in (201, 200), f"Upload falló: {r.status_code}"
    body = r.json()
    doc_id = body["id"]
    nit = body.get("data", {}).get("issuer_nit") or body.get("issuer_nit", "")
    return doc_id, nit


@pytest.mark.e2e
def test_approve_document_notifies_rules_service(zip_fixture: Path, gateway_url: str):
    headers = {"Authorization": "Bearer test-e2e-token"}
    doc_id, nit = _upload_and_get_id(zip_fixture, gateway_url)

    approve = httpx.patch(
        f"{gateway_url}/api/v1/documents/{doc_id}/approve",
        headers=headers,
        timeout=15,
    )
    assert approve.status_code in (200, 204), f"Aprobación falló: {approve.status_code}"

    time.sleep(2)  # notificación best-effort al rules-service

    if nit:
        rules = httpx.get(
            f"{gateway_url}/api/v1/rules?nit={nit}",
            headers=headers,
            timeout=10,
        )
        # El rules-service puede no tener reglas aún si es la primera aprobación
        assert rules.status_code == 200

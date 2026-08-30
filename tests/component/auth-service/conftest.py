"""
Setup para component tests de auth-service.
Auth-service crea su propia base de datos 'abacus_meta' y usa Redis.
Los tests se limitan a endpoints que no requieren estado previo.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[3] / "services" / "auth-service"))


@pytest.fixture()
def client():
    # auth-service lifespan intenta crear la DB — en CI con Postgres disponible funciona.
    # Se importa aquí (no al nivel del módulo) para que sys.path esté configurado primero.
    from app.main import app  # noqa: PLC0415

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

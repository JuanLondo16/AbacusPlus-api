"""
Fixtures para tests E2E.
El stack completo corre via docker compose — estos tests solo validan flujos finales.
"""

import zipfile
from pathlib import Path

import pytest

GATEWAY = "http://localhost:8000"
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples" / "xml"


@pytest.fixture(scope="session")
def zip_fixture(tmp_path_factory) -> Path:
    """Crea un ZIP con uno de los XMLs de muestra para subir al gateway."""
    tmp = tmp_path_factory.mktemp("e2e")
    xml_file = SAMPLES_DIR / "factura normal.xml"
    zip_path = tmp / "factura_test.zip"

    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(str(xml_file), arcname="factura_normal.xml")

    return zip_path


@pytest.fixture(scope="session")
def gateway_url() -> str:
    return GATEWAY

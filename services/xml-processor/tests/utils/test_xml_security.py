"""
Seguridad del parseo de XML.

El XML llega de terceros (ZIP descargado de la DIAN o carga manual del usuario), así que el
parseo usa defusedxml. `xml.etree.ElementTree` de la librería estándar acepta declaraciones
de entidades y es vulnerable a expansión de entidades («billion laughs»), con lo que un solo
archivo podría agotar la memoria y la CPU del servicio.

Estos tests fijan el comportamiento: un documento con DTD, entidades o referencias externas
se rechaza con ValueError antes de procesarse.
"""

import io
import zipfile
from unittest.mock import AsyncMock

import pytest
from app.utils.xml_parser import parse_xml
from app.utils.zip_handler import extract_zip_file

_BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<Invoice>&lol3;</Invoice>"""

_XXE_FILE_READ = """<?xml version="1.0"?>
<!DOCTYPE root [<!ENTITY secret SYSTEM "file:///etc/passwd">]>
<Invoice>&secret;</Invoice>"""

_XXE_SSRF = """<?xml version="1.0"?>
<!DOCTYPE root [<!ENTITY probe SYSTEM "http://169.254.169.254/latest/meta-data/">]>
<Invoice>&probe;</Invoice>"""


class TestParseXmlRejectsMaliciousDocuments:
    @pytest.mark.parametrize(
        "payload,ataque",
        [
            (_BILLION_LAUGHS, "expansión de entidades (agotamiento de memoria/CPU)"),
            (_XXE_FILE_READ, "XXE: lectura de archivos del servidor"),
            (_XXE_SSRF, "XXE: petición a un servicio interno (SSRF)"),
        ],
    )
    def test_rejects_payload(self, payload, ataque):
        with pytest.raises(ValueError) as exc:
            parse_xml(payload)

        assert "seguridad" in str(exc.value).lower(), f"debe rechazarse por {ataque}"

    def test_a_document_without_entities_is_still_parsed(self):
        """La protección no debe rechazar documentos legítimos: sin DTD, el flujo continúa."""
        result = parse_xml('<?xml version="1.0"?><Invoice></Invoice>')

        assert isinstance(result, dict)


def _zip_upload(xml: str, filename: str = "factura.xml") -> AsyncMock:
    """Mock de UploadFile con un ZIP en memoria, igual que en test_zip_handler."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, xml)
    buffer.seek(0)

    mock_file = AsyncMock()
    mock_file.read = AsyncMock(return_value=buffer.getvalue())
    return mock_file


class TestZipHandlerRejectsMaliciousXml:
    """El ZIP se valida antes de guardar: la defensa aplica en las dos puertas de entrada."""

    @pytest.mark.asyncio
    async def test_rejects_entity_expansion_inside_the_zip(self):
        with pytest.raises(ValueError) as exc:
            await extract_zip_file(_zip_upload(_BILLION_LAUGHS))

        assert "seguridad" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_accepts_a_plain_xml_inside_the_zip(self):
        content, filename = await extract_zip_file(_zip_upload("<Invoice><a>1</a></Invoice>"))

        assert filename == "factura.xml"
        assert "<Invoice>" in content

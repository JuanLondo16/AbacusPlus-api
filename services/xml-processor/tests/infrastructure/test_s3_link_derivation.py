"""
RF-03 — Composición del enlace cuando la API de subida no lo devuelve.

El alcance dice que «la API retorna un enlace que debe guardarse». El Lambda del cliente
confirma el guardado pero **no retorna URL**: responde con el nombre definitivo del objeto,
al que añade una marca de tiempo. Como el `path` lo enviamos nosotros, la clave queda
determinada y el enlace puede componerse sin pedirle un cambio al cliente.

Estas pruebas fijan esa composición y, sobre todo, que **no se invente un enlace** cuando
falta el dato para construirlo: un enlace incorrecto guardado en base es peor que ninguno,
porque el detalle mostraría un archivo roto sin señal de error.
"""

import pytest
from app.infrastructure.clients.s3_upload_client import (
    _derive_link,
    _extract_link,
    _lambda_filename,
)

# Respuesta real del Lambda del cliente, verificada contra el endpoint en producción.
_RESPUESTA_REAL = {
    "message": "Se ha guardado el archivo satisfactoriamente!",
    "filename": "FBC98359_pdf_2026-08-01_10_52_05.pdf",
    "data": {"ETag": '"1561dd53a0113ffc509cf3d3e767cf56"', "ServerSideEncryption": "AES256"},
}


@pytest.fixture
def bucket(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "abacus-documents")
    monkeypatch.setenv("S3_REGION", "ca-central-1")
    monkeypatch.delenv("S3_PUBLIC_BASE_URL", raising=False)


class TestTheRealResponseCarriesNoLink:
    def test_the_lambda_response_has_no_url_field(self):
        """Es la razón de existir de la composición: confirmarlo evita revertirla por error."""
        assert _extract_link(_RESPUESTA_REAL) is None


class TestComposition:
    def test_composes_the_object_url_from_path_and_filename(self, bucket):
        link = _derive_link(_RESPUESTA_REAL, "abacusplus/documentos/ikbo/")

        assert link == (
            "https://abacus-documents.s3.ca-central-1.amazonaws.com/"
            "abacusplus/documentos/ikbo/FBC98359_pdf_2026-08-01_10_52_05.pdf"
        )

    def test_an_explicit_public_base_wins(self, monkeypatch, bucket):
        """El bucket puede servirse por CloudFront o dominio propio; solo el cliente lo sabe."""
        monkeypatch.setenv("S3_PUBLIC_BASE_URL", "https://archivos.ikbo.com/")

        link = _derive_link(_RESPUESTA_REAL, "abacusplus/documentos/ikbo/")

        assert link.startswith("https://archivos.ikbo.com/abacusplus/documentos/ikbo/")

    def test_the_key_is_percent_encoded(self, bucket):
        """Un nombre con espacios produciría una URL inválida si no se codifica."""
        link = _derive_link({"filename": "factura con espacios.pdf"}, "docs/ikbo/")

        assert " " not in link
        assert "%20" in link

    def test_duplicate_slashes_are_not_produced(self, bucket):
        link = _derive_link({"filename": "/a.pdf"}, "docs/ikbo/")

        assert "//a.pdf" not in link.replace("https://", "")


class TestItNeverInventsALink:
    def test_returns_nothing_without_a_filename(self, bucket):
        assert _derive_link({"message": "ok"}, "docs/ikbo/") is None

    def test_returns_nothing_when_the_bucket_is_unknown(self, monkeypatch):
        """Sin bucket ni base pública no hay forma de saber dónde quedó el objeto."""
        monkeypatch.delenv("S3_PUBLIC_BASE_URL", raising=False)
        monkeypatch.setenv("S3_BUCKET", "")

        assert _derive_link(_RESPUESTA_REAL, "docs/ikbo/") is None

    def test_returns_nothing_for_a_non_dict_payload(self, bucket):
        assert _derive_link("ok", "docs/ikbo/") is None
        assert _derive_link(None, "docs/ikbo/") is None

    def test_returns_nothing_when_filename_is_not_text(self, bucket):
        assert _derive_link({"filename": 123}, "docs/ikbo/") is None


class TestAnExplicitLinkStillWins:
    def test_a_response_with_a_url_is_used_as_is(self):
        """Si el cliente actualiza su Lambda para retornar la URL, se prefiere esa."""
        assert _extract_link({"url": "https://cdn.ikbo.com/f.pdf"}) == "https://cdn.ikbo.com/f.pdf"

    def test_a_configured_field_name_is_honoured(self, monkeypatch):
        monkeypatch.setenv("S3_UPLOAD_LINK_FIELD", "enlace")

        assert (
            _extract_link({"enlace": "https://cdn.ikbo.com/f.pdf"}) == "https://cdn.ikbo.com/f.pdf"
        )


class TestLambdaFilename:
    """Nombre que se le envía al Lambda del cliente.

    Contrato verificado contra el endpoint real (2026-08-06): el Lambda añade la marca de
    tiempo Y la extensión, que deduce del CONTENIDO del archivo, no del nombre. Mandar la
    extensión produce claves con la extensión duplicada
    (`factura.pdf_2026-08-06_17_39_28.pdf`), que es lo que el cliente pidió evitar.
    """

    def test_strips_the_extension(self):
        assert _lambda_filename("FBC98359.pdf") == "FBC98359"

    def test_strips_the_extension_regardless_of_type(self):
        # El Lambda pone .xml solo, porque mira los bytes: nosotros no debemos sugerirla.
        assert _lambda_filename("FBC98359.xml") == "FBC98359"

    def test_keeps_a_name_that_has_no_extension(self):
        assert _lambda_filename("FBC98359") == "FBC98359"

    def test_only_the_last_extension_is_dropped(self):
        assert _lambda_filename("factura.2026.pdf") == "factura.2026"

    def test_sanitizes_characters_that_do_not_belong_in_an_s3_key(self):
        assert _lambda_filename("fac tura/rara?.pdf") == "fac_tura_rara_"

    def test_falls_back_to_a_default_when_there_is_no_name(self):
        assert _lambda_filename("") == "documento"

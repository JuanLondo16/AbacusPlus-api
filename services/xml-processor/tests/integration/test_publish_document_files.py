"""
RF-03 — Publicación del PDF y el XML en Amazon S3.

El alcance pide subir los archivos «consumiendo la API existente» y guardar el enlace que
retorna, para renderizarlo luego en el detalle. Estas pruebas fijan tres garantías:

- **Idempotencia.** La API de subida añade una marca de tiempo al nombre, así que cada
  llamada crea un objeto nuevo. Republicar sin querer duplicaría objetos en el bucket y
  cambiaría una URL que el contador puede tener abierta.
- **Independencia entre archivos.** Que falle el XML no puede costar el enlace del PDF.
- **Nada se pierde ante un fallo.** La subida es best-effort: el documento ya está
  guardado y una caída de la API no puede propagarse ni dejar datos a medias.
"""

from datetime import date, datetime, timezone

import app.infrastructure.persistence.models.concept  # noqa: F401
import app.infrastructure.persistence.models.document_tax  # noqa: F401
import app.infrastructure.persistence.models.issuer  # noqa: F401
import app.infrastructure.persistence.models.receiver  # noqa: F401
import app.infrastructure.persistence.models.tax  # noqa: F401
import pytest
from app.application.use_cases.publish_document_files import PublishDocumentFilesUseCase
from app.infrastructure.persistence.models.document import Document
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository

PDF = b"%PDF-1.4\ncontenido\n%%EOF\n"
XML = b"<Invoice><ID>FBC98359</ID></Invoice>"


class _FakeS3Client:
    """Doble de la API de subida: registra las llamadas en lugar de emitirlas."""

    def __init__(self, enabled=True, pdf_link="https://s3.example/pdf", xml_link="https://s3.example/xml"):
        self.enabled = enabled
        self._pdf_link = pdf_link
        self._xml_link = xml_link
        self.calls: list[tuple[str, str, str]] = []

    async def upload_pdf(self, data, filename, tenant_slug=""):
        self.calls.append(("pdf", filename, tenant_slug))
        return self._pdf_link

    async def upload_xml(self, data, filename, tenant_slug=""):
        self.calls.append(("xml", filename, tenant_slug))
        return self._xml_link


def _make_doc(db_session, **kwargs) -> Document:
    defaults = {
        "document_name": "test.xml",
        "document_number": "FBC98359",
        "date": date(2026, 4, 29),
        "hour": "10:00",
        "currency": "COP",
        "document_type": "Factura de venta",
        "uuid": "rf03-1",
        "issuer_name": "BODEGA Y COCINA SAS",
        "issuer_nit": "830044885",
        "receiver_name": "MI EMPRESA",
        "receiver_nit": "800987654",
        "subtotal": 148600.0,
        "total_taxes": 28234.0,
        "retefuente": 0.0,
        "reteica": 0.0,
        "total": 176834.0,
        "register_at": datetime.now(timezone.utc),
        "status": 200,
        "pdf_data": PDF,
        "xml_data": XML,
    }
    defaults.update(kwargs)
    doc = Document(**defaults)
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


@pytest.fixture
def repo(db_session):
    return DocumentRepository(db_session)


class TestPublication:
    @pytest.mark.asyncio
    async def test_publishes_both_files_and_persists_the_links(self, db_session, repo):
        doc = _make_doc(db_session)
        client = _FakeS3Client()

        result = await PublishDocumentFilesUseCase(repo, client).execute(doc.id, "ikbo")

        assert result["uploaded"] == ["pdf", "xml"]
        db_session.refresh(doc)
        assert doc.pdf_url == "https://s3.example/pdf"
        assert doc.xml_url == "https://s3.example/xml"

    @pytest.mark.asyncio
    async def test_the_tenant_reaches_the_upload_api(self, db_session, repo):
        """El path en el bucket separa los documentos por tenant."""
        doc = _make_doc(db_session)
        client = _FakeS3Client()

        await PublishDocumentFilesUseCase(repo, client).execute(doc.id, "ikbo")

        assert all(call[2] == "ikbo" for call in client.calls)

    @pytest.mark.asyncio
    async def test_the_filename_comes_from_the_document_number(self, db_session, repo):
        doc = _make_doc(db_session)
        client = _FakeS3Client()

        await PublishDocumentFilesUseCase(repo, client).execute(doc.id, "ikbo")

        assert ("pdf", "FBC98359.pdf", "ikbo") in client.calls
        assert ("xml", "FBC98359.xml", "ikbo") in client.calls

    @pytest.mark.asyncio
    async def test_a_document_number_with_odd_characters_is_sanitised(self, db_session, repo):
        """El nombre viaja en la clave del objeto: no puede llevar separadores de ruta."""
        doc = _make_doc(db_session, document_number="FB/C 98\\359", uuid="rf03-raro")
        client = _FakeS3Client()

        await PublishDocumentFilesUseCase(repo, client).execute(doc.id, "ikbo")

        nombre = next(c[1] for c in client.calls if c[0] == "pdf")
        assert "/" not in nombre and "\\" not in nombre and " " not in nombre

    @pytest.mark.asyncio
    async def test_a_missing_document_is_rejected(self, repo):
        with pytest.raises(ValueError):
            await PublishDocumentFilesUseCase(repo, _FakeS3Client()).execute(999999, "ikbo")


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_a_file_with_a_link_is_not_uploaded_again(self, db_session, repo):
        """La API añade una marca de tiempo: republicar duplicaría el objeto en el bucket."""
        doc = _make_doc(db_session, pdf_url="https://s3.example/ya-existe")
        client = _FakeS3Client()

        result = await PublishDocumentFilesUseCase(repo, client).execute(doc.id, "ikbo")

        assert "pdf" in result["skipped"]
        assert not any(c[0] == "pdf" for c in client.calls)
        db_session.refresh(doc)
        assert doc.pdf_url == "https://s3.example/ya-existe"

    @pytest.mark.asyncio
    async def test_overwrite_republishes_a_broken_link(self, db_session, repo):
        doc = _make_doc(db_session, pdf_url="https://s3.example/vencido")
        client = _FakeS3Client()

        await PublishDocumentFilesUseCase(repo, client).execute(doc.id, "ikbo", overwrite=True)

        db_session.refresh(doc)
        assert doc.pdf_url == "https://s3.example/pdf"

    @pytest.mark.asyncio
    async def test_running_twice_uploads_only_once(self, db_session, repo):
        doc = _make_doc(db_session)
        client = _FakeS3Client()
        uc = PublishDocumentFilesUseCase(repo, client)

        await uc.execute(doc.id, "ikbo")
        segunda = await uc.execute(doc.id, "ikbo")

        assert segunda["uploaded"] == []
        assert len(client.calls) == 2  # pdf y xml, de la primera ejecución


class TestPartialAndFailure:
    @pytest.mark.asyncio
    async def test_a_document_without_xml_only_publishes_the_pdf(self, db_session, repo):
        doc = _make_doc(db_session, xml_data=None)
        client = _FakeS3Client()

        result = await PublishDocumentFilesUseCase(repo, client).execute(doc.id, "ikbo")

        assert result["uploaded"] == ["pdf"]
        assert "xml" in result["skipped"]

    @pytest.mark.asyncio
    async def test_a_failing_xml_does_not_cost_the_pdf_link(self, db_session, repo):
        doc = _make_doc(db_session)
        client = _FakeS3Client(xml_link=None)

        result = await PublishDocumentFilesUseCase(repo, client).execute(doc.id, "ikbo")

        assert result["uploaded"] == ["pdf"]
        assert result["warnings"]
        db_session.refresh(doc)
        assert doc.pdf_url == "https://s3.example/pdf"

    @pytest.mark.asyncio
    async def test_a_failure_reports_an_actionable_warning(self, db_session, repo):
        doc = _make_doc(db_session)
        client = _FakeS3Client(pdf_link=None, xml_link=None)

        result = await PublishDocumentFilesUseCase(repo, client).execute(doc.id, "ikbo")

        assert result["uploaded"] == []
        assert any("reintente" in w.lower() for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_without_configuration_nothing_is_attempted(self, db_session, repo):
        """Sin la API configurada no se toca el documento ni se inventa un enlace."""
        doc = _make_doc(db_session)
        client = _FakeS3Client(enabled=False)

        result = await PublishDocumentFilesUseCase(repo, client).execute(doc.id, "ikbo")

        assert result["uploaded"] == []
        assert client.calls == []
        db_session.refresh(doc)
        assert doc.pdf_url is None

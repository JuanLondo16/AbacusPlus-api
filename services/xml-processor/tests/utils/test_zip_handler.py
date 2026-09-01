import io
import zipfile
from unittest.mock import AsyncMock

import pytest
from app.utils.zip_handler import extract_zip_file


def _create_mock_zip_upload(xml_content: str, filename: str = "invoice.xml") -> AsyncMock:
    """Create an UploadFile mock with a ZIP in memory."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, xml_content)
    buffer.seek(0)

    mock_file = AsyncMock()
    mock_file.read = AsyncMock(return_value=buffer.getvalue())
    return mock_file


def _create_mock_empty_zip() -> AsyncMock:
    """Create an UploadFile mock with an empty ZIP (no XML)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("readme.txt", "not an xml file")
    buffer.seek(0)

    mock_file = AsyncMock()
    mock_file.read = AsyncMock(return_value=buffer.getvalue())
    return mock_file


VALID_XML = '<?xml version="1.0"?><root><data>test</data></root>'


class TestExtractZipFile:
    @pytest.mark.asyncio
    async def test_extract_valid_zip(self):
        mock_file = _create_mock_zip_upload(VALID_XML)
        content, filename, xml_bytes, pdf_bytes = await extract_zip_file(mock_file)
        assert content == VALID_XML
        assert filename == "invoice.xml"
        assert xml_bytes == VALID_XML.encode("utf-8")
        assert pdf_bytes is None

    @pytest.mark.asyncio
    async def test_no_xml_in_zip(self):
        mock_file = _create_mock_empty_zip()
        with pytest.raises(ValueError, match="No valid XML files found"):
            await extract_zip_file(mock_file)

    @pytest.mark.asyncio
    async def test_file_too_large(self):
        mock_file = _create_mock_zip_upload(VALID_XML)
        with pytest.raises(ValueError, match="exceeds maximum size"):
            await extract_zip_file(mock_file, max_file_size=1)  # 1 byte limit

    @pytest.mark.asyncio
    async def test_invalid_zip(self):
        mock_file = AsyncMock()
        mock_file.read = AsyncMock(return_value=b"not a zip file at all")
        with pytest.raises(ValueError, match="not a valid ZIP"):
            await extract_zip_file(mock_file)

    @pytest.mark.asyncio
    async def test_zip_with_invalid_xml(self):
        mock_file = _create_mock_zip_upload("<invalid>xml</broken>")
        with pytest.raises(ValueError, match="does not contain valid XML"):
            await extract_zip_file(mock_file)

    @pytest.mark.asyncio
    async def test_ignores_macosx_files(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("__MACOSX/._hidden.xml", "<fake/>")
            zf.writestr("real_invoice.xml", VALID_XML)
        buffer.seek(0)

        mock_file = AsyncMock()
        mock_file.read = AsyncMock(return_value=buffer.getvalue())

        content, filename, xml_bytes, pdf_bytes = await extract_zip_file(mock_file)
        assert filename == "real_invoice.xml"
        assert content == VALID_XML
        assert xml_bytes == VALID_XML.encode("utf-8")
        assert pdf_bytes is None


class TestExtractZipFilePreservesOfficialBackup:
    """RF-03: la carga manual debe respaldar el XML y, si el ZIP lo trae, el PDF oficial.

    Antes, `extract_zip_file` solo devolvía el texto decodificado del XML para poder
    parsearlo; los bytes crudos no salían de la función, así que `process_xml.py` nunca
    tenía nada que guardar en `document.xml_data`/`pdf_data`, y `GET /documents/{id}/pdf|xml`
    respondía 404 para cualquier documento cargado a mano.
    """

    @pytest.mark.asyncio
    async def test_xml_only_zip_still_returns_the_raw_xml_bytes(self):
        mock_file = _create_mock_zip_upload(VALID_XML)
        _content, _filename, xml_bytes, pdf_bytes = await extract_zip_file(mock_file)

        assert xml_bytes == VALID_XML.encode("utf-8")
        assert pdf_bytes is None

    @pytest.mark.asyncio
    async def test_zip_with_pdf_returns_both_official_files(self):
        buffer = io.BytesIO()
        pdf_content = b"%PDF-1.4 fake but valid signature"
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("invoice.xml", VALID_XML)
            zf.writestr("invoice.pdf", pdf_content)
        buffer.seek(0)

        mock_file = AsyncMock()
        mock_file.read = AsyncMock(return_value=buffer.getvalue())

        _content, _filename, xml_bytes, pdf_bytes = await extract_zip_file(mock_file)

        assert xml_bytes == VALID_XML.encode("utf-8")
        assert pdf_bytes == pdf_content

    @pytest.mark.asyncio
    async def test_a_pdf_without_the_pdf_signature_is_discarded(self):
        """Igual que la descarga automática: solo se acepta un PDF real (firma `%PDF-`)."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("invoice.xml", VALID_XML)
            zf.writestr("invoice.pdf", b"not actually a pdf")
        buffer.seek(0)

        mock_file = AsyncMock()
        mock_file.read = AsyncMock(return_value=buffer.getvalue())

        _content, _filename, _xml_bytes, pdf_bytes = await extract_zip_file(mock_file)

        assert pdf_bytes is None

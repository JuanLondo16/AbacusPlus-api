"""
RF-03 · La carga manual (`POST /documents`) debe guardar el respaldo oficial del documento.

`ProcessXmlUseCase._extract_content` solo devolvía el TEXTO decodificado del XML —lo que
necesita `parse_xml`— y descartaba los bytes crudos; `extract_zip_file` ni siquiera miraba si
el ZIP traía un PDF. `execute()` nunca asignaba `document.pdf_data`/`document.xml_data`, así
que un documento cargado a mano quedaba sin ningún soporte descargable: ni el enlace S3 (que
se deriva de esos bytes) ni el respaldo propio del backend (`GET /documents/{id}/pdf|xml`,
que responde 404 sin ellos) tenían de dónde sacarlo.

La descarga automática desde la DIAN (`infrastructure/queue/download_queue.py`) sí guardaba
ambos campos; estas pruebas fijan que la carga manual haga exactamente lo mismo, para los dos
casos: un ZIP con XML+PDF y un ZIP con solo XML (el `.xml` suelto no trae PDF nunca).
"""

import io
import zipfile
from unittest.mock import AsyncMock

import app.infrastructure.persistence.models.concept  # noqa: F401
import app.infrastructure.persistence.models.issuer  # noqa: F401
import app.infrastructure.persistence.models.receiver  # noqa: F401
import app.infrastructure.persistence.models.tax  # noqa: F401
import pytest
from app.application.use_cases.process_xml import ProcessXmlUseCase
from app.infrastructure.persistence.repositories.concept_repository import ConceptRepository
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository
from app.infrastructure.persistence.repositories.issuer_repository import IssuerRepository
from app.infrastructure.persistence.repositories.receiver_repository import ReceiverRepository
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository

# Misma factura base que tests/utils/test_xml_parser.py: IVA 19%, una línea, CUFE y medio de
# pago. Basta con lo que `parse_xml` necesita para construir un documento válido.
_BASE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>FE-BACKUP-001</cbc:ID>
    <cbc:UUID schemeName="CUFE-SHA384">cufe-backup-001</cbc:UUID>
    <cbc:IssueDate>2024-01-15</cbc:IssueDate>
    <cbc:IssueTime>10:30:00</cbc:IssueTime>
    <cbc:DueDate>2024-02-15</cbc:DueDate>
    <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
    <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
    <cac:AccountingSupplierParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyName><cbc:Name>Empresa Emisora SAS</cbc:Name></cac:PartyName>
            <cac:PartyTaxScheme>
                <cbc:CompanyID schemeID="31">900123456</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
            <cac:Contact>
                <cbc:Telephone>3001234567</cbc:Telephone>
                <cbc:ElectronicMail>emisor@test.com</cbc:ElectronicMail>
            </cac:Contact>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyName><cbc:Name>Empresa Receptora LTDA</cbc:Name></cac:PartyName>
            <cac:PartyTaxScheme>
                <cbc:CompanyID schemeID="31">800987654</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
            <cac:Contact>
                <cbc:Telephone>3009876543</cbc:Telephone>
                <cbc:ElectronicMail>receptor@test.com</cbc:ElectronicMail>
            </cac:Contact>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:PaymentMeans>
        <cbc:PaymentMeansCode>49</cbc:PaymentMeansCode>
        <cbc:PaymentDueDate>2024-02-15</cbc:PaymentDueDate>
    </cac:PaymentMeans>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="94">10</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="COP">1000000</cbc:LineExtensionAmount>
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="COP">190000</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="COP">1000000</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="COP">190000</cbc:TaxAmount>
                <cac:TaxCategory>
                    <cbc:Percent>19</cbc:Percent>
                    <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
                </cac:TaxCategory>
            </cac:TaxSubtotal>
        </cac:TaxTotal>
        <cac:Item>
            <cbc:Description>Servicio de consultoria</cbc:Description>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="COP">100000</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="COP">190000</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="COP">1000000</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="COP">190000</cbc:TaxAmount>
            <cac:TaxCategory>
                <cbc:Percent>19</cbc:Percent>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="COP">1000000</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="COP">1000000</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="COP">1190000</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="COP">1190000</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>"""

_PDF_SIGNATURE = b"%PDF-1.4 fake but valid signature"


def _upload_zip(entries: dict) -> AsyncMock:
    """Mock de UploadFile con un ZIP en memoria, con un archivo por entrada de `entries`."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    buffer.seek(0)

    mock_file = AsyncMock()
    mock_file.filename = "carga.zip"
    mock_file.read = AsyncMock(return_value=buffer.getvalue())
    return mock_file


def _upload_plain_xml(content: str) -> AsyncMock:
    mock_file = AsyncMock()
    mock_file.filename = "factura.xml"
    mock_file.read = AsyncMock(return_value=content.encode("utf-8"))
    return mock_file


@pytest.fixture
def use_case(db_session):
    return ProcessXmlUseCase(
        document_repo=DocumentRepository(db_session),
        issuer_repo=IssuerRepository(db_session),
        receiver_repo=ReceiverRepository(db_session),
        tax_repo=TaxRepository(db_session),
        concept_repo=ConceptRepository(db_session),
    )


class TestCargaManualGuardaElRespaldoOficial:
    @pytest.mark.asyncio
    async def test_zip_con_xml_y_pdf_guarda_ambos(self, use_case, db_session):
        upload = _upload_zip({"factura.xml": _BASE_XML, "factura.pdf": _PDF_SIGNATURE})

        result = await use_case.execute(upload)

        doc = DocumentRepository(db_session).get_by_id(result["document_id"])
        assert doc.xml_data == _BASE_XML.encode("utf-8")
        assert doc.pdf_data == _PDF_SIGNATURE
        assert doc.pdf_source == "dian_official"

    @pytest.mark.asyncio
    async def test_zip_con_solo_xml_guarda_el_xml_y_deja_el_pdf_vacio(self, use_case, db_session):
        upload = _upload_zip({"factura.xml": _BASE_XML})

        result = await use_case.execute(upload)

        doc = DocumentRepository(db_session).get_by_id(result["document_id"])
        assert doc.xml_data == _BASE_XML.encode("utf-8")
        assert doc.pdf_data is None

    @pytest.mark.asyncio
    async def test_xml_suelto_tambien_guarda_sus_bytes(self, use_case, db_session):
        upload = _upload_plain_xml(_BASE_XML)

        result = await use_case.execute(upload)

        doc = DocumentRepository(db_session).get_by_id(result["document_id"])
        assert doc.xml_data == _BASE_XML.encode("utf-8")
        assert doc.pdf_data is None

import logging
from datetime import datetime
from fastapi import UploadFile

from app.utils.zip_handler import extract_zip_file
from app.utils.xml_parser import parse_xml
from app.utils.dian_dv import dv_calculate
from app.infrastructure.persistence.models.document import Document, DocumentDetail
from app.infrastructure.persistence.models.issuer import Issuer
from app.infrastructure.persistence.models.receiver import Receiver
from app.infrastructure.persistence.models.tax import Tax
from app.infrastructure.persistence.models.concept import ConceptDescription
from app.domain.ports.repositories import (
    DocumentRepositoryPort,
    IssuerRepositoryPort,
    ReceiverRepositoryPort,
    TaxRepositoryPort,
    ConceptRepositoryPort,
)
from app.domain.exceptions.base import DuplicateEntityException, FileProcessingException

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'xml', 'zip'}


class ProcessXmlUseCase:
    def __init__(
        self,
        document_repo: DocumentRepositoryPort,
        issuer_repo: IssuerRepositoryPort,
        receiver_repo: ReceiverRepositoryPort,
        tax_repo: TaxRepositoryPort,
        concept_repo: ConceptRepositoryPort,
    ):
        self.document_repo = document_repo
        self.issuer_repo = issuer_repo
        self.receiver_repo = receiver_repo
        self.tax_repo = tax_repo
        self.concept_repo = concept_repo

    async def execute(self, file: UploadFile) -> dict:
        xml_content, filename = await self._extract_content(file)
        xml_data = parse_xml(xml_content)
        if not xml_data:
            raise FileProcessingException("Failed to parse XML. Please verify the file content.")

        logger.info("Processing document: %s", filename)

        duplicate = self.document_repo.get_by_document_number(
            xml_data.get('numero_documento', '')
        )
        if duplicate:
            doc_number = xml_data.get('numero_documento', '')
            raise DuplicateEntityException("Document", doc_number)

        self._ensure_issuer(xml_data)
        self._ensure_receiver(xml_data)
        self._ensure_tax(xml_data)
        document = self._build_document(xml_data, filename)
        self._build_details(document, xml_data)

        created = self.document_repo.create(document)
        logger.info("Document created with ID: %d", created.id)

        return {
            "status": "success",
            "data": {
                "id": created.id,
                "document_name": created.document_name,
                "document_number": created.document_number,
                "date": str(created.date),
                "issuer_name": created.issuer_name,
                "receiver_name": created.receiver_name,
                "total": created.total,
                "status": created.status,
                "details_count": len(created.details),
            },
            "document_id": created.id,
            "filename": filename,
        }

    async def _extract_content(self, file: UploadFile) -> tuple[str, str]:
        file_extension = file.filename.split('.')[-1].lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            raise FileProcessingException(
                "File format not allowed. Only ZIP and XML files are accepted."
            )

        if file_extension == 'zip':
            xml_content, filename = await extract_zip_file(file)
        else:
            xml_bytes = await file.read()
            xml_content = xml_bytes.decode('utf-8')
            filename = file.filename

        return xml_content, filename

    def _ensure_issuer(self, xml_data: dict) -> None:
        emisor = xml_data.get('emisor', {})
        nit = emisor.get('nit', '')
        if not self.issuer_repo.get_by_nit(nit):
            contacto = emisor.get('contacto', {})
            issuer = Issuer(
                name=emisor.get('nombre', ''),
                nit=nit,
                dv=dv_calculate(nit),
                phone=contacto.get('telefono', ''),
                email=contacto.get('email', ''),
            )
            self.issuer_repo.create(issuer)
            logger.info("Issuer created: %s (NIT: %s)", issuer.name, nit)

    def _ensure_receiver(self, xml_data: dict) -> None:
        receptor = xml_data.get('receptor', {})
        nit = receptor.get('nit', '')
        if not self.receiver_repo.get_by_nit(nit):
            contacto = receptor.get('contacto', {})
            receiver = Receiver(
                name=receptor.get('nombre', ''),
                nit=nit,
                dv=dv_calculate(nit),
                phone=contacto.get('telefono', ''),
                email=contacto.get('email', ''),
            )
            self.receiver_repo.create(receiver)
            logger.info("Receiver created: %s (NIT: %s)", receiver.name, nit)

    def _ensure_tax(self, xml_data: dict) -> None:
        receptor = xml_data.get('receptor', {})
        impuestos = xml_data.get('impuestos', [])
        if not impuestos:
            return

        receiver_nit = receptor.get('nit', '')
        tax_name = impuestos[0].get('nombre', '')

        if not self.tax_repo.get_by_receiver_and_name(receiver_nit, tax_name):
            tax = Tax(
                receiver_nit=receiver_nit,
                tax=tax_name,
                percentage=impuestos[0].get('porcentaje', 0),
            )
            self.tax_repo.create(tax)
            logger.info("Tax created: %s for NIT: %s", tax_name, receiver_nit)

    def _build_document(self, xml_data: dict, filename: str) -> Document:
        emisor = xml_data.get('emisor', {})
        receptor = xml_data.get('receptor', {})
        totales = xml_data.get('totales', {})
        contacto_emisor = emisor.get('contacto', {})
        contacto_receptor = receptor.get('contacto', {})

        return Document(
            document_name=filename,
            document_number=xml_data.get('numero_documento', ''),
            date=datetime.strptime(xml_data.get('fecha_emision', ''), '%Y-%m-%d'),
            hour=xml_data.get('hora_emision', ''),
            currency=xml_data.get('moneda', ''),
            document_type=xml_data.get('tipo_documento', ''),
            uuid=xml_data.get('uuid', ''),
            issuer_name=emisor.get('nombre', ''),
            issuer_nit=emisor.get('nit', ''),
            issuer_phone=contacto_emisor.get('telefono', ''),
            issuer_email=contacto_emisor.get('email', ''),
            receiver_name=receptor.get('nombre', ''),
            receiver_nit=receptor.get('nit', ''),
            receiver_phone=contacto_receptor.get('telefono', ''),
            receiver_email=contacto_receptor.get('email', ''),
            subtotal=float(totales.get('subtotal', 0)),
            total_taxes=float(totales.get('total_impuestos', 0)),
            total=float(totales.get('total', 0)),
            status='Procesado',
        )

    def _build_details(self, document: Document, xml_data: dict) -> None:
        receptor = xml_data.get('receptor', {})
        receiver_nit = receptor.get('nit', '')

        for item in xml_data.get('items', []):
            description = item.get('descripcion', '')
            matched = self.concept_repo.find_matching_description(receiver_nit, description)

            if matched:
                concept_description_id = matched.id
            else:
                new_concept = ConceptDescription(
                    receiver_nit=receiver_nit,
                    description=description,
                )
                created = self.concept_repo.create_description(new_concept)
                concept_description_id = created.id
                logger.info("ConceptDescription created: '%s'", description[:50])

            item_taxes = item.get('impuestos', [{}])
            first_tax = item_taxes[0] if item_taxes else {}

            detail = DocumentDetail(
                description=description,
                concept_description_id=concept_description_id,
                quantity=float(item.get('cantidad', 0)),
                unit=item.get('unidad_medida', ''),
                price=float(item.get('precio_unitario', 0)),
                subtotal=float(item.get('valor_total', 0)),
                tax_type=first_tax.get('porcentaje', 0),
                tax_value=float(first_tax.get('valor', 0)),
                total=float(item.get('valor_total', 0)) + float(first_tax.get('valor', 0)),
            )
            document.details.append(detail)

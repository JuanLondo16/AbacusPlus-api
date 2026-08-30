"""RF-03 · Publicación del PDF y el XML del documento en Amazon S3.

El alcance describe el flujo así: el sistema descompone el ZIP de la DIAN, sube el PDF
(y opcionalmente el XML) al bucket **consumiendo la API existente**, y guarda en la base
el enlace que ésta retorna para poder renderizarlo en el detalle.

Este caso de uso concentra ese paso. Antes vivía embebido en el trabajador de descargas,
con dos consecuencias: los documentos cargados manualmente nunca obtenían enlace, y no
existía forma de reintentar la subida de un documento cuyo enlace hubiera fallado. Al
extraerlo, la misma lógica sirve a las dos rutas de ingreso y a la reparación posterior.

Los bytes se leen de la base, no del ZIP: son la fuente de verdad que ya quedó almacenada,
así que un documento se puede publicar en cualquier momento posterior a su procesamiento.
"""

import logging
import re
from typing import Optional

from app.infrastructure.clients.s3_upload_client import S3UploadClient
from app.infrastructure.persistence.models.document import Document
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository

logger = logging.getLogger(__name__)

# El nombre viaja en el path del objeto en S3: se acota al juego de caracteres seguro para
# una clave, igual que hacía el trabajador de descargas.
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(document: Document, ext: str) -> str:
    numero = _UNSAFE_NAME.sub("_", str(document.document_number or "")).strip("_")
    return f"{numero or 'documento'}.{ext}"


class PublishDocumentFilesUseCase:
    """Sube a S3 los archivos ya almacenados de un documento y persiste sus enlaces."""

    def __init__(self, document_repo: DocumentRepository, client: Optional[S3UploadClient] = None):
        self._repo = document_repo
        self._client = client or S3UploadClient()

    async def execute(
        self, document_id: int, tenant_slug: str = "", overwrite: bool = False
    ) -> dict:
        """Publica el PDF y el XML de un documento.

        `overwrite=False` respeta los enlaces ya guardados: republicar un documento que ya
        está en S3 gastaría ancho de banda y cambiaría una URL que el contador puede tener
        abierta. Se envía `true` cuando se quiere rehacer un enlace roto o vencido.

        Best-effort por archivo: que falle el XML no impide guardar el enlace del PDF.
        """
        document = self._repo.get_by_id(document_id)
        if document is None:
            raise ValueError(f"Documento {document_id} no encontrado")

        if not self._client.enabled:
            return {
                "document_id": document_id,
                "pdf_url": document.pdf_url,
                "xml_url": document.xml_url,
                "uploaded": [],
                "skipped": ["pdf", "xml"],
                "warnings": ["La subida a S3 no está configurada; no se publicó ningún archivo."],
            }

        uploaded: list[str] = []
        skipped: list[str] = []
        warnings: list[str] = []

        pdf_link = await self._publish(
            document,
            "pdf",
            document.pdf_data,
            document.pdf_url,
            tenant_slug,
            overwrite,
            skipped,
            warnings,
        )
        if pdf_link:
            uploaded.append("pdf")

        xml_link = await self._publish(
            document,
            "xml",
            document.xml_data,
            document.xml_url,
            tenant_slug,
            overwrite,
            skipped,
            warnings,
        )
        if xml_link:
            uploaded.append("xml")

        if uploaded:
            actualizado = self._repo.update_file_urls(
                document_id, pdf_url=pdf_link, xml_url=xml_link
            )
            document = actualizado or document

        return {
            "document_id": document_id,
            "pdf_url": document.pdf_url,
            "xml_url": document.xml_url,
            "uploaded": uploaded,
            "skipped": skipped,
            "warnings": warnings,
        }

    async def _publish(
        self,
        document: Document,
        kind: str,
        data: Optional[bytes],
        current_url: Optional[str],
        tenant_slug: str,
        overwrite: bool,
        skipped: list[str],
        warnings: list[str],
    ) -> Optional[str]:
        """Sube un archivo concreto. Retorna el enlace nuevo, o None si no se publicó."""
        if not data:
            skipped.append(kind)
            return None
        if current_url and not overwrite:
            skipped.append(kind)
            return None

        filename = _safe_filename(document, kind)
        subir = self._client.upload_pdf if kind == "pdf" else self._client.upload_xml
        link = await subir(data, filename, tenant_slug)

        if not link:
            # El cliente ya registró la causa concreta; aquí se traduce a algo accionable
            # para quien consume la respuesta desde la interfaz.
            warnings.append(
                f"No se pudo publicar el {kind.upper()} en S3. "
                "Revise la conectividad con la API de subida y reintente."
            )
            return None
        return link

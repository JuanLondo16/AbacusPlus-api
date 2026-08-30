"""RF-08: publicación y retirada del conocimiento contable validado del RAG.

La regla de RF-08 es una sola y se enuncia en negativo: **una causación no es conocimiento
hasta que el documento está CONTABILIZADO**. Mientras esté en Procesado, Causado o Aprobado
no hay nada que indexar, porque hasta que SIIGO no acepta la factura no consta que la
imputación sea contablemente válida: puede fallar por un tercero mal creado, un comprobante
mal configurado o una cuenta que no admite movimiento, y todos esos casos son exactamente
los que no deben servir de ejemplo.

Este publicador es el único punto por el que entra ese conocimiento. Se colocó aquí, en la
capa de aplicación, y no dentro de `AccountDocumentUseCase`, porque hay dos caminos
distintos por los que un documento llega a «Contabilizada» —el envío normal (RF-05) y la
reconciliación de un documento bloqueado (RF-06)— y ambos deben alimentar el RAG con el
mismo criterio. Una sola implementación evita que uno de los dos se quede atrás.

Todas las operaciones son best-effort: un fallo del rag-service no puede revertir una
contabilización que SIIGO ya aceptó. El conocimiento perdido se repone con el backfill
`POST /internal/documents/reindex`, que reconstruye desde los documentos contabilizados.
"""

import logging
from typing import Any, Mapping, Optional

from app.domain.services.rag_content import (
    build_accounted_knowledge_content,
    build_accounted_knowledge_metadata,
    build_accounted_knowledge_signature,
)
from app.domain.value_objects.document_status import DocumentStatus

logger = logging.getLogger(__name__)

#: Tipo de fuente con el que se indexan las causaciones en el rag-service.
INVOICE_SOURCE_TYPE = "invoice"


class AccountingKnowledgePublisher:
    """Convierte una causación contabilizada en conocimiento reutilizable del RAG."""

    def __init__(
        self,
        rag_client,
        tenant_slug: str,
        document_repo,
        tax_repo,
        integration_tax_repo=None,
        cost_center_repo=None,
        retention_repo=None,
    ):
        self._rag = rag_client
        self._tenant_slug = tenant_slug
        self._document_repo = document_repo
        self._tax_repo = tax_repo
        self._integration_tax_repo = integration_tax_repo
        self._cost_center_repo = cost_center_repo
        #: Tarifas de ReteICA. Aportan el municipio, que el documento de la DIAN no trae.
        self._retention_repo = retention_repo

    def publish(
        self,
        document_id: int,
        payload: Optional[Mapping[str, Any]] = None,
        siigo_id: Optional[str] = None,
        siigo_name: Optional[str] = None,
    ) -> bool:
        """Indexa la causación final de un documento contabilizado. True si se indexó.

        Vuelve a leer el documento de la base en lugar de confiar en lo que le pasen: la
        condición que habilita el aprendizaje es el estado persistido, y comprobarlo aquí
        —en el mismo sitio que indexa— es lo que hace que la regla no dependa de que cada
        uno de los llamadores se acuerde de comprobarla.
        """
        if self._rag is None or not self._tenant_slug:
            return False

        try:
            doc = self._document_repo.get_by_id(document_id)
            if doc is None:
                return False

            # La doble condición no es redundante: el estado dice que el flujo se completó y
            # el `siigo_id` dice contra qué comprobante real. Sin el segundo no hay forma de
            # auditar el conocimiento, y un documento marcado como contabilizado sin id sería
            # justamente el síntoma de una contabilización que no terminó bien.
            siigo_id = siigo_id or getattr(doc, "siigo_id", None)
            if doc.status != DocumentStatus.CONTABILIZADA or not siigo_id:
                logger.info(
                    "RF-08: el documento %s no genera conocimiento (estado=%s, siigo_id=%s)",
                    document_id,
                    DocumentStatus.NAMES.get(doc.status, doc.status),
                    siigo_id,
                )
                return False

            taxes = list(self._tax_repo.list_by_document(document_id))
            tax_names = self._tax_names()
            content = build_accounted_knowledge_content(
                document=doc,
                taxes=taxes,
                tax_name_map=tax_names,
                payload=payload,
                siigo_id=siigo_id,
                siigo_name=siigo_name or getattr(doc, "siigo_name", None),
                cost_center_name_map=self._cost_center_names(),
            )
            # Lo que se BUSCA no es lo que se lee: el texto de arriba lleva la plantilla que
            # comparten todas las causaciones, y embeberla haría que todas se parecieran
            # entre sí. La firma deja solo lo que distingue este caso.
            embedding_text = build_accounted_knowledge_signature(
                document=doc,
                taxes=taxes,
                tax_name_map=tax_names,
                payload=payload,
            )
            # RF-08 · búsqueda híbrida: los mismos hechos, en forma consultable. El texto
            # sirve para el parecido semántico; estos rasgos, para filtrar por lo que de
            # verdad hace comparables dos facturas (tercero, municipio, cuentas, retenciones).
            metadata = build_accounted_knowledge_metadata(
                document=doc,
                taxes=taxes,
                tax_name_map=tax_names,
                payload=payload,
                municipality_code=self._municipality_code(),
            )
            self._rag.index_chunk_internal(
                tenant_slug=self._tenant_slug,
                source_type=INVOICE_SOURCE_TYPE,
                source_id=document_id,
                content=content,
                embedding_text=embedding_text,
                is_validated=True,
                siigo_id=siigo_id,
                metadata=metadata,
            )
            logger.info(
                "RF-08: conocimiento validado indexado para el documento %s (SIIGO %s)",
                document_id,
                siigo_id,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "RF-08: no se pudo indexar el conocimiento del documento %s: %s",
                document_id,
                exc,
            )
            return False

    def revoke(self, document_id: int, motivo: str = "") -> bool:
        """Retira del RAG el conocimiento de un documento que dejó de estar contabilizado.

        Se invoca cuando una causación contabilizada se ajusta o se reversa. La alternativa
        —dejarla indexada— haría que el sistema siguiera proponiendo como precedente
        justamente la imputación que hubo que corregir, y el error se multiplicaría en cada
        documento parecido que llegara después. Entre perder un ejemplo y propagar uno malo,
        se pierde el ejemplo: el conocimiento correcto vuelve solo en cuanto el documento
        corregido se contabilice de nuevo.
        """
        if self._rag is None or not self._tenant_slug:
            return False
        try:
            self._rag.revoke_chunks_internal(
                tenant_slug=self._tenant_slug,
                source_type=INVOICE_SOURCE_TYPE,
                source_id=document_id,
            )
            logger.info(
                "RF-08: conocimiento retirado del documento %s%s",
                document_id,
                f" ({motivo})" if motivo else "",
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "RF-08: no se pudo retirar el conocimiento del documento %s: %s",
                document_id,
                exc,
            )
            return False

    # ── Catálogos para nombrar lo que el payload solo trae como id ─────────────

    def _tax_names(self) -> dict[int, str]:
        if self._integration_tax_repo is None:
            return {}
        try:
            return {t.id: t.name for t in self._integration_tax_repo.get_active()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("RF-08: catálogo de impuestos no disponible: %s", exc)
            return {}

    def _municipality_code(self) -> str:
        """Municipio del caso, tomado de las tarifas de ReteICA configuradas.

        El documento de la DIAN no dice en qué municipio se causa el ICA, y la única fuente
        de esa información en el sistema es la tabla de tarifas —la misma que decide dónde
        retiene la empresa—. Cuando hay un solo municipio configurado, que es lo habitual, el
        caso queda etiquetado con él y puede filtrarse por municipio. Con varios no se
        adivina: se deja sin etiquetar antes que atribuirle uno equivocado, porque un
        precedente con el municipio errado propone la tarifa de otra ciudad.
        """
        if self._retention_repo is None:
            return ""
        try:
            rates = self._retention_repo.get_ica_rates()
        except Exception as exc:  # noqa: BLE001
            logger.warning("RF-08: tarifas de ReteICA no disponibles: %s", exc)
            return ""
        codigos = {str(getattr(r, "municipality_code", "") or "").strip() for r in rates}
        codigos.discard("")
        return codigos.pop() if len(codigos) == 1 else ""

    def _cost_center_names(self) -> dict[int, str]:
        if self._cost_center_repo is None:
            return {}
        try:
            return {c.id: c.name for c in self._cost_center_repo.get_active()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("RF-08: catálogo de centros de costo no disponible: %s", exc)
            return {}

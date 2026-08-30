"""RF-06: buscar en SIIGO una factura de compra que quizá ya se creó.

Este caso de uso existe para cerrar el único desenlace que la contabilización no puede
resolver por sí sola. Cuando la llamada a `POST /v1/purchases` termina en un timeout, un
corte de red o una respuesta ilegible, no se sabe si SIIGO llegó a registrar la factura. El
documento queda entonces en «Contabilizando», que no es un indicador de progreso sino un
cerrojo: `/v1/purchases` no admite `Idempotency-Key`, de modo que reenviarlo puede crear un
segundo asiento real en la contabilidad del cliente.

La salida de ese cerrojo es preguntar. Aquí se pregunta.

Por qué se filtra en memoria y no en SIIGO
------------------------------------------
`GET /v1/purchases` admite filtrar por rango de fechas de creación, pero no por el número de
factura del proveedor, que es justo el dato que identifica al documento de la DIAN. Así que
se acota por fecha —lo que SIIGO sí sabe hacer— y la coincidencia por número se resuelve
aquí. El rango es estrecho a propósito: cada página consume cupo del límite de 100
peticiones por minuto que SIIGO aplica por empresa.
"""

import logging
from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.application.dto.purchase_invoice import (
    FindPurchaseInvoiceResponse,
    PurchaseInvoiceMatch,
)
from app.application.use_cases.manage_credentials import ManageCredentialsUseCase
from app.infrastructure.siigo.siigo_client import SiigoApiClient

logger = logging.getLogger(__name__)

_PURCHASES_PATH = "/v1/purchases"

#: Margen a cada lado de la fecha del documento. SIIGO registra el comprobante con la fecha
#: que se le envía, que es la del documento de la DIAN, pero un desfase de zona horaria o una
#: fecha corregida a mano pueden moverlo un día. Dos días de margen cubren ambos casos sin
#: convertir la búsqueda en un barrido.
_MARGEN_DIAS = 2


class FindPurchaseInvoiceUseCase:
    def __init__(self, credentials: ManageCredentialsUseCase):
        self.credentials = credentials

    def execute(
        self,
        account_key: Optional[str],
        provider_invoice_number: str,
        document_date: Optional[date_type] = None,
    ) -> FindPurchaseInvoiceResponse:
        """Devuelve las facturas de SIIGO que coinciden con el número de factura buscado.

        Una lista vacía es una respuesta útil, y la más importante: significa que SIIGO no
        creó nada y que el documento puede reenviarse sin riesgo de duplicar.
        """
        numero = (provider_invoice_number or "").strip()
        if not numero:
            # Sin número no hay forma de identificar la factura, y devolver «no encontrada»
            # sería peligroso: invitaría a reenviar un documento que quizá sí existe.
            raise ValueError(
                "No se puede buscar en SIIGO sin el número de factura del proveedor."
            )

        desde, hasta = self._rango(document_date)

        client = self._cliente(account_key)

        params: dict[str, Any] = {}
        if desde and hasta:
            params["created_start"] = desde.isoformat()
            params["created_end"] = hasta.isoformat()

        crudas = self._consultar(client, params)
        coincidencias = [
            self._to_match(f) for f in crudas if self._coincide(f, numero)
        ]

        logger.info(
            "Reconciliación SIIGO: %s comprobantes revisados, %s coinciden con '%s'",
            len(crudas),
            len(coincidencias),
            numero,
        )

        return FindPurchaseInvoiceResponse(
            matches=coincidencias,
            searched_provider_invoice_number=numero,
            searched_from=desde.isoformat() if desde else None,
            searched_to=hasta.isoformat() if hasta else None,
        )

    # ── Consulta ───────────────────────────────────────────────────────────────

    def _cliente(self, account_key: Optional[str]) -> SiigoApiClient:
        """Resuelve la credencial de la empresa y devuelve el cliente ya autenticado.

        Aislado en su propio método para que las pruebas puedan sustituir el salto a SIIGO
        sin montar credenciales ni base de datos: lo que interesa verificar aquí es la lógica
        de coincidencia, no el manejo del token, que ya cubre `ManageCredentialsUseCase`.
        """
        credential = self.credentials.ensure_token(account_key)
        return SiigoApiClient(credential)

    @staticmethod
    def _consultar(client: SiigoApiClient, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Recorre las páginas de `GET /v1/purchases` dentro del rango indicado."""
        resultados: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = client.get(_PURCHASES_PATH, params={**params, "page": page, "page_size": 100})
            pagina = SiigoApiClient._extract_results(payload)
            resultados.extend(pagina)

            paginacion = (
                payload.get("pagination") or payload.get("value", {}).get("pagination") or {}
            )
            try:
                total = int(paginacion.get("total_results") or len(resultados))
            except (TypeError, ValueError):
                total = len(resultados)

            if not pagina or len(resultados) >= total:
                break
            page += 1
            # Cortafuegos: si SIIGO devolviera una paginación incoherente, no se puede quedar
            # girando indefinidamente contra un servicio con cupo limitado.
            if page > 20:
                logger.warning("Reconciliación SIIGO: se alcanzó el límite de 20 páginas")
                break
        return resultados

    @staticmethod
    def _rango(document_date: Optional[date_type]) -> tuple[Optional[date_type], Optional[date_type]]:
        if document_date is None:
            return None, None
        return (
            document_date - timedelta(days=_MARGEN_DIAS),
            document_date + timedelta(days=_MARGEN_DIAS),
        )

    # ── Coincidencia ───────────────────────────────────────────────────────────

    @classmethod
    def _coincide(cls, factura: dict[str, Any], numero: str) -> bool:
        """True si la factura de SIIGO corresponde al número de factura del proveedor.

        La comparación normaliza mayúsculas y espacios porque el número viaja como texto
        libre y SIIGO lo devuelve tal cual se guardó.
        """
        registrado = cls._provider_number(factura)
        if not registrado:
            return False
        return registrado.strip().upper() == numero.strip().upper()

    @staticmethod
    def _provider_number(factura: dict[str, Any]) -> Optional[str]:
        provider = factura.get("provider_invoice") or {}
        if isinstance(provider, dict):
            numero = provider.get("number")
            return str(numero) if numero is not None else None
        return None

    @staticmethod
    def _provider_prefix(factura: dict[str, Any]) -> Optional[str]:
        provider = factura.get("provider_invoice") or {}
        if isinstance(provider, dict):
            prefijo = provider.get("prefix")
            return str(prefijo) if prefijo is not None else None
        return None

    @classmethod
    def _to_match(cls, factura: dict[str, Any]) -> PurchaseInvoiceMatch:
        return PurchaseInvoiceMatch(
            siigo_id=str(factura.get("id") or ""),
            siigo_name=factura.get("name"),
            date=str(factura["date"]) if factura.get("date") is not None else None,
            total=cls._decimal(factura.get("total")),
            provider_invoice_number=cls._provider_number(factura),
            provider_invoice_prefix=cls._provider_prefix(factura),
        )

    @staticmethod
    def _decimal(valor: Any) -> Optional[Decimal]:
        if valor is None:
            return None
        try:
            return Decimal(str(valor))
        except (InvalidOperation, ValueError):
            return None

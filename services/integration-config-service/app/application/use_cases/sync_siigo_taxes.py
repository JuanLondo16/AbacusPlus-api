import logging
from datetime import datetime, timezone
from typing import Any

from app.application.dto.retention import SyncSiigoRetentionsResponse
from app.domain.exceptions.base import EntityNotFoundException
from app.domain.services.retention_classification import classify
from app.infrastructure.clients.siigo_client import SiigoApiClient, token_expiration_from_response
from app.infrastructure.persistence.repositories.integration_repository import (
    IntegrationCredentialRepository,
)
from app.infrastructure.persistence.repositories.retention_repository import RetentionRepository
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository

logger = logging.getLogger(__name__)

_SIIGO_PROVIDER = "siigo"
_TAXES_PATH = "/v1/taxes"


class SyncSiigoTaxesUseCase:
    """Sincroniza `GET /v1/taxes` de SIIGO y reparte cada fila según su naturaleza tributaria.

    SIIGO mezcla en un único endpoint los impuestos reales del documento (IVA, Impoconsumo,
    AdValorem) y las retenciones (ReteFuente, ReteICA, ReteIVA, Autorretención), distinguidas
    solo por `type`. Antes de esta separación TODO se guardaba en `integration_taxes`; ahora
    cada fila se enruta a la tabla que le corresponde:

    - Impuestos → `integration_taxes` (TaxRepository, sin cambios respecto a antes).
    - ReteIVA / Retefuente / Autorretención → `integration_retentions` (RetentionRepository).
    - ReteICA → SE DESCARTA, con un log explícito. SIIGO no conoce municipios: su ReteICA es
      un porcentaje plano (p. ej. "ReteICA 6.9") que no se puede verificar contra ningún
      municipio ni concepto real. Guardarlo sería reproducir exactamente el problema que
      motivó esta migración — una tarifa sin poder confirmarse contra la realidad territorial
      del tributo. El ReteICA se alimenta ÚNICAMENTE de la importación de Excel con
      municipios (`ImportRetentionsUseCase` / `POST /integrations/retentions/imports`).
    """

    def __init__(
        self,
        credential_repository: IntegrationCredentialRepository,
        tax_repository: TaxRepository,
        retention_repository: RetentionRepository,
    ):
        self.credential_repository = credential_repository
        self.tax_repository = tax_repository
        self.retention_repository = retention_repository

    def execute(self) -> SyncSiigoRetentionsResponse:
        credentials = self.credential_repository.list(provider=_SIIGO_PROVIDER)
        if not credentials:
            raise EntityNotFoundException("IntegrationCredential", "siigo")

        credential = credentials[0]
        account_key = credential.account_key

        client = SiigoApiClient(credential)
        self._ensure_token(client, account_key)

        payload = client.get(_TAXES_PATH)
        raw_items = SiigoApiClient._extract_results(payload)

        taxes: list[dict[str, Any]] = []
        retentions: list[dict[str, Any]] = []
        reteica_ignored = 0
        for item in raw_items:
            mapped = self._map_item(item)
            clase = classify(mapped["type"])
            if clase == "reteica":
                reteica_ignored += 1
                logger.info(
                    "SIIGO sync: se descarta la fila ReteICA '%s' (id=%s, %s%%). SIIGO no "
                    "conoce municipios; el ReteICA se alimenta solo de la importación de "
                    "Excel con municipios.",
                    mapped["name"],
                    mapped["id"],
                    mapped["percentage"],
                )
            elif clase in ("retefuente", "reteiva", "autorretencion"):
                retentions.append(mapped)
            else:
                # iva, impoconsumo, advalorem, o algo que este código todavía no reconoce —
                # en cualquiera de los dos últimos casos, se trata como impuesto (comportamiento
                # anterior a esta separación) y no se pierde silenciosamente.
                taxes.append(mapped)

        taxes_imported = self.tax_repository.upsert_many(taxes)
        retentions_imported = self.retention_repository.upsert_siigo_many(retentions)

        return SyncSiigoRetentionsResponse(
            taxes_imported=taxes_imported,
            retentions_imported=retentions_imported,
            reteica_ignored=reteica_ignored,
            retentions=self.retention_repository.list(),
            taxes=self.tax_repository.list(),
        )

    def _ensure_token(self, client: SiigoApiClient, account_key: str) -> None:
        credential = client.credential
        now = datetime.now(timezone.utc)
        expires_at = credential.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if credential.access_token and expires_at and expires_at > now:
            return

        auth_response = client.authenticate()
        new_expires_at = token_expiration_from_response(auth_response)

        credential.access_token = auth_response["access_token"]
        credential.token_type = auth_response.get("token_type", "Bearer")
        credential.expires_at = new_expires_at

        self.credential_repository.save_token(
            provider=_SIIGO_PROVIDER,
            account_key=account_key,
            access_token=auth_response["access_token"],
            token_type=auth_response.get("token_type", "Bearer"),
            expires_at=new_expires_at,
        )

    @staticmethod
    def _map_item(item: dict[str, Any]) -> dict[str, Any]:
        # El `id` es el dato que hace útil al resto: es el identificador con el que SIIGO
        # reconoce el impuesto/retención cuando se lo devolvemos en `retentions` o en
        # `items[].taxes`. Omitirlo dejaba que la tabla generara claves propias con su
        # secuencia, y esas claves locales viajaban a SIIGO como si fueran suyas: `The id
        # doesn't exist`.
        return {
            "id": item.get("id"),
            "name": str(item.get("name") or item.get("id") or ""),
            "type": str(item.get("type") or ""),
            "percentage": float(item.get("percentage") or item.get("rate") or 0),
            "active": item.get("active", True),
        }

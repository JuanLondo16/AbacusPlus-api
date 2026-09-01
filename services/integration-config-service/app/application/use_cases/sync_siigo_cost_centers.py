from datetime import datetime, timezone
from typing import Any, Optional

from app.application.dto.cost_center import ImportCostCentersResponse
from app.domain.exceptions.base import EntityNotFoundException
from app.infrastructure.clients.siigo_client import SiigoApiClient, token_expiration_from_response
from app.infrastructure.clients.xml_processor_client import XmlProcessorClient
from app.infrastructure.persistence.repositories.cost_center_repository import CostCenterRepository
from app.infrastructure.persistence.repositories.integration_repository import (
    IntegrationCredentialRepository,
)

_SIIGO_PROVIDER = "siigo"
_COST_CENTERS_PATH = "/v1/cost-centers"


class SyncSiigoCostCentersUseCase:
    def __init__(
        self,
        credential_repository: IntegrationCredentialRepository,
        cost_center_repository: CostCenterRepository,
        tenant_slug: str,
        xml_processor_client: Optional[XmlProcessorClient] = None,
    ):
        self.credential_repository = credential_repository
        self.cost_center_repository = cost_center_repository
        self.tenant_slug = tenant_slug
        self.xml_processor_client = xml_processor_client or XmlProcessorClient()

    def execute(self) -> ImportCostCentersResponse:
        credentials = self.credential_repository.list(provider=_SIIGO_PROVIDER)
        if not credentials:
            raise EntityNotFoundException("IntegrationCredential", "siigo")

        credential = credentials[0]
        account_key = credential.account_key
        client = SiigoApiClient(credential)
        self._ensure_token(client, account_key)

        payload = client.get(_COST_CENTERS_PATH)
        raw_items = SiigoApiClient._extract_results(payload)

        cost_centers = [self._map_item(item) for item in raw_items]
        imported = self.cost_center_repository.upsert_many(cost_centers, deactivate_missing=True)

        # El catálogo que consume el frontend vive en `cost_centers` (xml-processor). Sin esta
        # proyección la sincronización quedaría aislada en `integration_cost_centers` y el
        # selector de centro de costo seguiría vacío.
        self.xml_processor_client.project_cost_centers(
            tenant_slug=self.tenant_slug,
            items=[
                {"code": cc["code"], "name": cc["name"], "active": cc["active"]}
                for cc in cost_centers
            ],
        )

        return ImportCostCentersResponse(
            imported=imported,
            cost_centers=self.cost_center_repository.list(),
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
        return {
            "external_id": str(item["id"]) if item.get("id") is not None else None,
            "code": str(item.get("code") or item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "active": item.get("active", True),
            "raw_payload": item,
        }

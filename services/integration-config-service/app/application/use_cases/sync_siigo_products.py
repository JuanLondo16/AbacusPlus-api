from datetime import datetime, timezone
from typing import Any

from app.application.dto.product import ImportProductsResponse
from app.domain.exceptions.base import EntityNotFoundException
from app.infrastructure.clients.siigo_client import SiigoApiClient, token_expiration_from_response
from app.infrastructure.persistence.repositories.integration_repository import (
    IntegrationCredentialRepository,
)
from app.infrastructure.persistence.repositories.product_repository import ProductRepository

_SIIGO_PROVIDER = "siigo"
_PRODUCTS_PATH = "/v1/products"


class SyncSiigoProductsUseCase:
    def __init__(
        self,
        credential_repository: IntegrationCredentialRepository,
        product_repository: ProductRepository,
    ):
        self.credential_repository = credential_repository
        self.product_repository = product_repository

    def execute(self) -> ImportProductsResponse:
        credentials = self.credential_repository.list(provider=_SIIGO_PROVIDER)
        if not credentials:
            raise EntityNotFoundException("IntegrationCredential", "siigo")

        credential = credentials[0]
        account_key = credential.account_key
        client = SiigoApiClient(credential)
        self._ensure_token(client, account_key)

        payload = client.get(_PRODUCTS_PATH)
        raw_items = SiigoApiClient._extract_results(payload)

        products = [self._map_item(item) for item in raw_items]
        imported = self.product_repository.upsert_many(products, deactivate_missing=True)

        return ImportProductsResponse(
            imported=imported,
            products=self.product_repository.list(),
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
            "code": str(item.get("code") or item.get("id") or ""),
            "type": str(item.get("type") or "").lower(),
            "description": str(item.get("description") or item.get("name") or ""),
            "active": item.get("active", True),
            "raw_payload": item,
        }

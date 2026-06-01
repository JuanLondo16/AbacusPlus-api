from datetime import datetime, timezone
from typing import Any

from app.application.dto.tax import ImportTaxesResponse
from app.domain.exceptions.base import EntityNotFoundException
from app.infrastructure.clients.siigo_client import SiigoApiClient, token_expiration_from_response
from app.infrastructure.persistence.repositories.integration_repository import (
    IntegrationCredentialRepository,
)
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository

_SIIGO_PROVIDER = "siigo"
_TAXES_PATH = "/v1/taxes"


class SyncSiigoTaxesUseCase:
    def __init__(
        self,
        credential_repository: IntegrationCredentialRepository,
        tax_repository: TaxRepository,
    ):
        self.credential_repository = credential_repository
        self.tax_repository = tax_repository

    def execute(self, account_key: str = "default") -> ImportTaxesResponse:
        credential = self.credential_repository.get(
            provider=_SIIGO_PROVIDER, account_key=account_key
        )
        if credential is None:
            raise EntityNotFoundException("IntegrationCredential", f"siigo/{account_key}")

        client = SiigoApiClient(credential)
        self._ensure_token(client, account_key)

        payload = client.get(_TAXES_PATH)
        raw_items = SiigoApiClient._extract_results(payload)

        taxes = [self._map_item(item) for item in raw_items]
        imported = self.tax_repository.upsert_many(taxes)

        return ImportTaxesResponse(imported=imported, taxes=self.tax_repository.list())

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
            "name": str(item.get("name") or item.get("id") or ""),
            "type": str(item.get("type") or ""),
            "percentage": float(item.get("percentage") or item.get("rate") or 0),
            "active": item.get("active", True),
        }

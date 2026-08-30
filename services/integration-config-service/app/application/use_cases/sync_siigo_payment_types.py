from datetime import datetime, timezone
from typing import Any

from app.application.dto.payment_type import ImportPaymentTypesResponse
from app.domain.exceptions.base import EntityNotFoundException
from app.infrastructure.clients.siigo_client import SiigoApiClient, token_expiration_from_response
from app.infrastructure.persistence.repositories.integration_repository import (
    IntegrationCredentialRepository,
)
from app.infrastructure.persistence.repositories.payment_type_repository import (
    PaymentTypeRepository,
)

_SIIGO_PROVIDER = "siigo"
_PAYMENT_TYPES_PATH = "/v1/payment-types"
_DEFAULT_DOCUMENT_TYPE = "FC"


class SyncSiigoPaymentTypesUseCase:
    def __init__(
        self,
        credential_repository: IntegrationCredentialRepository,
        payment_type_repository: PaymentTypeRepository,
    ):
        self.credential_repository = credential_repository
        self.payment_type_repository = payment_type_repository

    def execute(self) -> ImportPaymentTypesResponse:
        credentials = self.credential_repository.list(provider=_SIIGO_PROVIDER)
        if not credentials:
            raise EntityNotFoundException("IntegrationCredential", "siigo")

        credential = credentials[0]
        account_key = credential.account_key
        client = SiigoApiClient(credential)
        self._ensure_token(client, account_key)

        document_type = (
            (credential.extra_config or {}).get("default_document_type") or _DEFAULT_DOCUMENT_TYPE
        )

        payload = client.get(_PAYMENT_TYPES_PATH, params={"document_type": document_type})
        raw_items = SiigoApiClient._extract_results(payload)

        payment_types = [self._map_item(item, document_type) for item in raw_items]
        imported = self.payment_type_repository.upsert_many(payment_types, deactivate_missing=True)

        return ImportPaymentTypesResponse(
            imported=imported,
            payment_types=self.payment_type_repository.list(),
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
    def _map_item(item: dict[str, Any], document_type: str) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "name": str(item.get("name") or item.get("id") or ""),
            "type": str(item.get("type") or document_type),
            "active": item.get("active", True),
        }

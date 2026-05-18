from typing import Optional

from app.application.dto.integration import CredentialUpsertRequest
from app.domain.exceptions.base import ValidationException
from app.infrastructure.persistence.repositories.integration_repository import IntegrationCredentialRepository


class ManageCredentialsUseCase:
    def __init__(self, repository: IntegrationCredentialRepository):
        self.repository = repository

    def upsert(self, request: CredentialUpsertRequest):
        provider = request.provider.strip().lower()
        account_key = request.account_key.strip()
        if not provider:
            raise ValidationException("provider is required")
        if not account_key:
            raise ValidationException("account_key is required")

        return self.repository.upsert(
            provider=provider,
            account_key=account_key,
            username=request.username,
            access_key=request.access_key,
            base_url=str(request.base_url),
            partner_id=request.partner_id,
            auth_scheme=request.auth_scheme,
            extra_config=request.extra_config,
        )

    def list(self, provider: Optional[str] = None):
        return self.repository.list(provider=provider.strip().lower() if provider else None)

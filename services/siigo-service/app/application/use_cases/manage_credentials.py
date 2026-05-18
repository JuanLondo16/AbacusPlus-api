from datetime import datetime, timezone

from app.application.dto.integration import AuthResponse, CredentialUpsertRequest
from app.domain.exceptions.base import EntityNotFoundException, ValidationException
from app.infrastructure.persistence.repositories.integration_repository import IntegrationCredentialRepository
from app.infrastructure.siigo.siigo_client import SiigoApiClient, token_expiration_from_response


class ManageCredentialsUseCase:
    def __init__(self, repository: IntegrationCredentialRepository):
        self.repository = repository

    def upsert(self, request: CredentialUpsertRequest):
        if request.provider.lower() != "siigo":
            raise ValidationException("This endpoint only manages SIIGO credentials for now")

        extra_config = {}
        if request.chart_accounts_path:
            extra_config["chart_accounts_path"] = request.chart_accounts_path

        return self.repository.upsert(
            provider=request.provider.lower(),
            account_key=request.account_key,
            username=request.username,
            access_key=request.access_key,
            base_url=str(request.base_url),
            partner_id=request.partner_id,
            extra_config=extra_config,
        )

    def authenticate(self, account_key: str = "default") -> AuthResponse:
        credential = self.repository.get("siigo", account_key)
        if credential is None:
            raise EntityNotFoundException("SIIGO credential", account_key)

        data = SiigoApiClient(credential).authenticate()
        expires_at = token_expiration_from_response(data)
        self.repository.save_token(
            credential=credential,
            access_token=data["access_token"],
            token_type=data.get("token_type") or "Bearer",
            expires_at=expires_at,
        )
        return AuthResponse(access_token_saved=True, token_type=data.get("token_type") or "Bearer", expires_at=expires_at)

    def ensure_token(self, account_key: str = "default"):
        credential = self.repository.get("siigo", account_key)
        if credential is None:
            raise EntityNotFoundException("SIIGO credential", account_key)

        if credential.access_token and credential.expires_at and credential.expires_at > datetime.now(timezone.utc):
            return credential

        self.authenticate(account_key=account_key)
        refreshed = self.repository.get("siigo", account_key)
        if refreshed is None:
            raise EntityNotFoundException("SIIGO credential", account_key)
        return refreshed
